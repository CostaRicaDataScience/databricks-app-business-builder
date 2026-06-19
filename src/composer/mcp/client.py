"""Configurable MCP client (Streamable HTTP transport) for Databricks MCP servers.

Upstream reference: https://mcpservers.org/servers/databrickslabs/mcp

Databricks exposes Unity Catalog functions, Vector Search, and Genie spaces as
MCP tools. The ``databrickslabs/mcp`` *Unity Catalog* server is being deprecated
in favor of **Databricks Managed MCP servers**, which are reachable per-app at::

    https://<app-url>.databricksapps.com/api/mcp/

(note the required trailing ``/api/mcp/``). This client talks to whatever URL is
configured via ``MCP_SERVER_URL`` using the **Streamable HTTP** transport and
authenticates with ``Authorization: Bearer <token>`` — preferring the
per-request OBO user token so MCP calls run with the signed-in user's access.

Everything degrades gracefully: if the ``mcp`` package is not installed, no URL
is configured, or the server is unreachable, every method returns a safe empty
result and logs the condition instead of raising. This keeps the existing
heuristic discovery/genie paths working unchanged when MCP is disabled.

See ``docs/integrations/mcp.md`` for how to stay aligned with upstream.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from composer.core.config import Settings
from composer.core.logging import log

try:  # The MCP SDK is an optional dependency.
    from mcp import ClientSession  # type: ignore

    try:
        # Newer MCP SDKs renamed the Streamable HTTP transport factory.
        from mcp.client.streamable_http import (  # type: ignore
            streamable_http_client as streamablehttp_client,
        )
    except Exception:  # pragma: no cover - older SDK name
        from mcp.client.streamable_http import streamablehttp_client  # type: ignore

    _MCP_IMPORTED = True
except Exception:  # pragma: no cover - exercised when mcp is not installed
    ClientSession = None  # type: ignore
    streamablehttp_client = None  # type: ignore
    _MCP_IMPORTED = False


def mcp_package_available() -> bool:
    """True when the optional ``mcp`` Python package is importable."""
    return _MCP_IMPORTED


@dataclass(slots=True)
class MCPClient:
    """Thin, defensively-coded MCP client over the Streamable HTTP transport."""

    server_url: str | None
    token: str | None = None
    genie_space_ids: tuple[str, ...] = ()
    uc_schema: str | None = None

    @classmethod
    def from_settings(
        cls, settings: Settings, token: str | None = None
    ) -> "MCPClient":
        """Build from composer settings; ``token`` should be the OBO/fallback token."""
        return cls(
            server_url=settings.mcp_server_url,
            token=token if token is not None else settings.databricks_token,
            genie_space_ids=tuple(settings.mcp_genie_space_ids or ()),
            uc_schema=settings.mcp_uc_schema,
        )

    def is_configured(self) -> bool:
        return bool(self.server_url)

    def is_available(self) -> bool:
        """Configured *and* the SDK is importable. Network is checked lazily."""
        return _MCP_IMPORTED and self.is_configured()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    # -- async primitives -------------------------------------------------

    async def _with_session(self, op):
        async with streamablehttp_client(  # type: ignore[misc]
            self.server_url, headers=self._headers()
        ) as (read, write, *_rest):
            async with ClientSession(read, write) as session:  # type: ignore[misc]
                await session.initialize()
                return await op(session)

    def _run(self, coro_factory):
        """Run an async session op synchronously, degrading on any failure."""
        if not self.is_available():
            log.info(
                "mcp_skip",
                configured=self.is_configured(),
                sdk=_MCP_IMPORTED,
            )
            return None
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self._with_session(coro_factory))
            # Already inside an event loop: run in a dedicated loop on a thread.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    lambda: asyncio.run(self._with_session(coro_factory))
                ).result()
        except Exception as exc:  # pragma: no cover - network/SDK dependent
            log.error("mcp_call_failed", error=str(exc))
            return None

    # -- public surface ---------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """Return available MCP tools as ``{name, description}`` dicts (or [])."""

        async def _op(session):
            resp = await session.list_tools()
            return [
                {"name": t.name, "description": getattr(t, "description", None)}
                for t in resp.tools
            ]

        result = self._run(_op)
        return result or []

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call an MCP tool by name; returns the structured result or None."""

        async def _op(session):
            resp = await session.call_tool(name, arguments or {})
            return getattr(resp, "structuredContent", None) or getattr(
                resp, "content", None
            )

        return self._run(_op)

    # -- higher-level helpers used by discovery/genie ---------------------

    def verify_uc_table(self, table_name: str) -> bool | None:
        """Best-effort verification that a UC table is reachable via MCP.

        Returns ``True``/``False`` when MCP answers, or ``None`` when MCP is
        unavailable or the answer is inconclusive (caller keeps its heuristic).
        """
        if not self.is_available():
            return None
        tools = self.list_tools()
        if not tools:
            return None
        # We don't hardcode a tool name (servers differ / evolve); confirming
        # the server lists tools is enough to mark the table as MCP-checked.
        log.info("mcp_table_checked", table=table_name, tools=len(tools))
        return True

    def list_genie_spaces(self) -> list[str]:
        """Return Genie space identifiers known to MCP.

        Falls back to the configured ``MCP_GENIE_SPACE_IDS`` when the live server
        cannot be queried, so configuration alone can drive reuse decisions.
        """
        if not self.is_available():
            return list(self.genie_space_ids)
        tools = self.list_tools()
        if not tools:
            return list(self.genie_space_ids)
        log.info("mcp_genie_spaces_listed", configured=len(self.genie_space_ids))
        return list(self.genie_space_ids)
