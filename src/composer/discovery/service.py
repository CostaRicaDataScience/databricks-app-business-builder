"""Discovery services for tables/genies and permissions.

By default discovery is heuristic (no workspace access required). When an
:class:`composer.mcp.client.MCPClient` is supplied *and available*, table and
Genie statuses are additionally verified against the configured Databricks MCP
server (Unity Catalog / Genie spaces). MCP verification only ever *augments*
the heuristic result and degrades safely to it when MCP is not configured or
reachable, so existing behavior is unchanged when MCP is disabled.
"""

from __future__ import annotations

import uuid

from composer.genie.resolver import is_search_request, resolve_genie_status
from composer.models.blueprint import DiscoveryReport, DiscoveryResourceStatus
from composer.models.intake import IntakeSpec


class DiscoveryService:
    """Discover and validate tables/Genies.

    Verification preference order, most to least authoritative:

    1. ``workspace`` — a live ``composer.databricks.client.DatabricksClient``
       (built from the OBO user token). Tables are checked against Unity Catalog
       and Genies are searched on the workspace.
    2. ``mcp_client`` — a configured Databricks MCP server (augments results).
    3. Heuristic — only when nothing above can verify; statuses are reported as
       ``unknown`` so we never falsely claim a resource "exists".
    """

    def __init__(self, mcp_client: object | None = None, workspace: object | None = None) -> None:
        self.mcp_client = mcp_client
        self.workspace = workspace

    def _mcp_active(self) -> bool:
        client = self.mcp_client
        return bool(client is not None and getattr(client, "is_available", lambda: False)())

    def _workspace_live(self) -> bool:
        ws = self.workspace
        return bool(ws is not None and getattr(ws, "has_real_client", lambda: False)())

    def run(self, intake: IntakeSpec) -> DiscoveryReport:
        mcp_active = self._mcp_active()
        workspace_live = self._workspace_live()

        tables = [self._discover_table(t, workspace_live, mcp_active) for t in intake.gold_tables]
        genies = self._discover_genies(intake, workspace_live, mcp_active)

        if workspace_live:
            summary = "Discovery report generated (verified against the workspace)."
        elif mcp_active:
            summary = "Discovery report generated (MCP-verified)."
        else:
            summary = (
                "Discovery report generated without a workspace connection: "
                "resources are reported as unknown until you connect."
            )
        return DiscoveryReport(
            report_id=str(uuid.uuid4()), tables=tables, genies=genies, summary=summary
        )

    # -- tables -----------------------------------------------------------

    def _discover_table(
        self, table: str, workspace_live: bool, mcp_active: bool
    ) -> DiscoveryResourceStatus:
        # 1) Real Unity Catalog check via the OBO workspace client.
        if workspace_live:
            info = self.workspace.inspect_table(table)  # type: ignore[attr-defined]
            if info is not None:
                if not info["exists"]:
                    return DiscoveryResourceStatus(
                        name=table, status="missing", details="No encontrada en Unity Catalog"
                    )
                if not info["has_description"] or info["missing_columns"]:
                    missing = ", ".join(info["missing_columns"][:5])
                    detail = "Faltan descripciones"
                    if missing:
                        detail += f" en columnas: {missing}"
                    return DiscoveryResourceStatus(
                        name=table, status="needs_enrichment", details=detail
                    )
                return DiscoveryResourceStatus(
                    name=table, status="exists", details="Verificada en Unity Catalog"
                )
        # 2) MCP augmentation (best-effort).
        if mcp_active:
            verified = self.mcp_client.verify_uc_table(table)  # type: ignore[attr-defined]
            if verified:
                return DiscoveryResourceStatus(
                    name=table, status="exists", details="Verificada vía MCP"
                )
        # 3) Honest fallback: we did not actually verify it.
        return DiscoveryResourceStatus(
            name=table,
            status="unknown",
            details="No verificada: conéctate a Databricks para validar esta tabla.",
        )

    # -- genies -----------------------------------------------------------

    def _discover_genies(
        self, intake: IntakeSpec, workspace_live: bool, mcp_active: bool
    ) -> list[DiscoveryResourceStatus]:
        # Real search of the user's Genie spaces (best-effort) when connected.
        searched_spaces: list[dict] | None = None
        if workspace_live:
            searched_spaces = self.workspace.search_genie_spaces()  # type: ignore[attr-defined]
        space_titles = [
            (s.get("title") or s.get("id") or "")
            for s in (searched_spaces or [])
            if (s.get("title") or s.get("id"))
        ]

        mcp_spaces: list[str] = []
        if mcp_active:
            mcp_spaces = self.mcp_client.list_genie_spaces()  # type: ignore[attr-defined]
        known_spaces = space_titles or mcp_spaces

        genies: list[DiscoveryResourceStatus] = []
        had_search_request = False
        for genie in intake.existing_genies:
            if is_search_request(genie):
                had_search_request = True
                genies.extend(
                    self._handle_genie_search(
                        searched_spaces, space_titles, workspace_live
                    )
                )
                continue
            status_value, details = resolve_genie_status(
                genie, genie_spaces=known_spaces, mcp_active=mcp_active or workspace_live
            )
            genies.append(
                DiscoveryResourceStatus(name=genie, status=status_value, details=details)
            )

        # If the user gave no genie input at all but we can search, offer reuse.
        if not intake.existing_genies and workspace_live and space_titles:
            for title in space_titles[:5]:
                genies.append(
                    DiscoveryResourceStatus(
                        name=title, status="exists", details="Genie encontrado en el workspace (posible reúso)"
                    )
                )

        return genies

    @staticmethod
    def _handle_genie_search(
        searched_spaces: list[dict] | None,
        space_titles: list[str],
        workspace_live: bool,
    ) -> list[DiscoveryResourceStatus]:
        if not workspace_live or searched_spaces is None:
            return [
                DiscoveryResourceStatus(
                    name="(búsqueda de Genie)",
                    status="unknown",
                    details=(
                        "No se pudo buscar asistentes: conéctate a Databricks para "
                        "que busquemos Genies existentes."
                    ),
                )
            ]
        if space_titles:
            return [
                DiscoveryResourceStatus(
                    name=title,
                    status="exists",
                    details="Genie encontrado en el workspace (posible reúso)",
                )
                for title in space_titles[:5]
            ]
        return [
            DiscoveryResourceStatus(
                name="(nuevo asistente)",
                status="needs_creation",
                details="No se encontró un Genie existente; se recomienda crear uno.",
            )
        ]
