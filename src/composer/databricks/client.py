"""Databricks SDK client wrapper with safe fallback mode."""

from __future__ import annotations

from dataclasses import dataclass, replace

from composer.core.config import Settings
from composer.core.logging import log
from composer.databricks.obo import MODE_OBO, RequestAuth

try:
    from databricks.sdk import WorkspaceClient  # type: ignore
except Exception:  # pragma: no cover
    WorkspaceClient = None  # type: ignore


@dataclass(slots=True)
class DatabricksClient:
    settings: Settings
    workspace_client: object | None
    # When this client was built from a forwarded user token (OBO), these record
    # the active mode + identity for status reporting. The token itself is held
    # only on the live ``workspace_client`` and never stored/logged here.
    auth_mode_override: str | None = None
    principal_override: str | None = None
    # Sanitized reason the per-request/SDK client could not be built (never the
    # token). Surfaced in connection_status so failures are diagnosable.
    init_error: str | None = None

    @classmethod
    def for_request(cls, settings: Settings, auth: RequestAuth) -> "DatabricksClient":
        """Build a *per-request* client honoring OBO when a user token is present.

        Falls back to :meth:`from_settings` (env/profile/service-principal) when
        no forwarded user token is available. Never caches the user token.
        """
        if not auth.is_obo:
            return cls.from_settings(settings)
        host = auth.host or settings.databricks_host
        if WorkspaceClient is None:
            log.info("databricks_sdk_unavailable", mode="obo_mock")
            return cls(
                settings=settings,
                workspace_client=None,
                auth_mode_override=MODE_OBO,
                principal_override=auth.principal,
                init_error="databricks-sdk is not installed in this runtime",
            )
        try:
            # Per-request client scoped to the user's forwarded OAuth token.
            # ``auth_type="pat"`` is REQUIRED inside Databricks Apps: the runtime
            # already exports the app service principal's OAuth env vars
            # (DATABRICKS_CLIENT_ID/SECRET). Without pinning the auth type, the
            # SDK sees both the env OAuth creds and this token and aborts with
            # "more than one authorization method configured". Pinning to PAT
            # makes it use *only* the forwarded user token (true OBO).
            client = WorkspaceClient(
                host=host, token=auth.user_token, auth_type="pat"
            )
            return cls(
                settings=replace(settings, databricks_host=host),
                workspace_client=client,
                auth_mode_override=MODE_OBO,
                principal_override=auth.principal,
            )
        except Exception as exc:  # pragma: no cover - depends on live SDK/env
            log.error("databricks_obo_init_failed", error=str(exc))
            return cls(
                settings=settings,
                workspace_client=None,
                auth_mode_override=MODE_OBO,
                principal_override=auth.principal,
                init_error=str(exc),
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatabricksClient":
        if WorkspaceClient is None:
            log.info("databricks_sdk_unavailable", mode="mock")
            return cls(settings=settings, workspace_client=None)
        try:
            if settings.auth_mode == "service_principal":
                client = WorkspaceClient(
                    host=settings.databricks_host,
                    client_id=settings.sp_client_id,
                    client_secret=settings.sp_client_secret,
                )
            elif settings.databricks_profile:
                client = WorkspaceClient(profile=settings.databricks_profile)
            else:
                client = WorkspaceClient(
                    host=settings.databricks_host,
                    token=settings.databricks_token,
                )
            return cls(settings=settings, workspace_client=client)
        except Exception as exc:  # pragma: no cover
            log.error("databricks_sdk_init_failed", error=str(exc))
            return cls(settings=settings, workspace_client=None)

    def has_real_client(self) -> bool:
        return self.workspace_client is not None

    def list_resource_names(
        self, service: str, method: str = "list", **kwargs
    ) -> list[str] | None:
        """Best-effort GET of a workspace resource collection by name.

        ``service`` is the ``WorkspaceClient`` attribute (e.g. ``serving_endpoints``,
        ``volumes``) and ``method`` its listing call. Returns a list of names, or
        ``None`` when we cannot read it (no client, unsupported on this SDK, or
        the call failed) so callers can honestly report "not checked".
        """
        if self.workspace_client is None:
            return None
        service_obj = getattr(self.workspace_client, service, None)
        if service_obj is None:
            return None
        fn = getattr(service_obj, method, None)
        if not callable(fn):
            return None
        try:
            raw = fn(**kwargs)
            names: list[str] = []
            for item in raw:
                name = (
                    getattr(item, "name", None)
                    or getattr(item, "full_name", None)
                    or getattr(item, "title", None)
                )
                if name:
                    names.append(str(name))
            return names
        except Exception as exc:  # pragma: no cover - depends on live workspace/SDK
            log.info("resource_list_failed", service=service, error=str(exc))
            return None

    def inspect_table(self, full_name: str) -> dict | None:
        """Verify a Unity Catalog table against the live workspace.

        Returns a dict ``{exists, has_description, missing_columns}`` when a real
        client is available, or ``None`` when we cannot verify (no client) — so
        callers stay honest and never claim a table "exists" without checking.
        """
        if self.workspace_client is None:
            return None
        try:
            table = self.workspace_client.tables.get(full_name=full_name)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - depends on live workspace
            log.info("uc_table_not_found", table=full_name, error=str(exc))
            return {"exists": False, "has_description": False, "missing_columns": []}
        comment = getattr(table, "comment", None)
        columns = getattr(table, "columns", None)
        missing_columns: list[str] = []
        # Only iterate real, list-shaped column collections (guards against
        # SDK shape changes and mocks that aren't iterable as expected).
        if isinstance(columns, (list, tuple)):
            missing_columns = [
                getattr(c, "name", "?")
                for c in columns
                if not getattr(c, "comment", None)
            ]
        return {
            "exists": True,
            "has_description": isinstance(comment, str) and bool(comment),
            "missing_columns": missing_columns,
        }

    def search_genie_spaces(self) -> list[dict] | None:
        """List Genie spaces visible to the authenticated user (best-effort).

        Returns a list of ``{id, title}`` dicts when the SDK exposes a listing
        API, or ``None`` when we cannot search (no client / unsupported SDK) so
        the caller can honestly report that no search was performed.
        """
        if self.workspace_client is None:
            return None
        genie = getattr(self.workspace_client, "genie", None)
        if genie is None:
            return None
        for method_name in ("list_spaces", "list"):
            method = getattr(genie, method_name, None)
            if method is None:
                continue
            try:
                raw = method()
            except Exception as exc:  # pragma: no cover - depends on live workspace
                log.info("genie_list_failed", method=method_name, error=str(exc))
                return None
            items = getattr(raw, "spaces", None)
            if not isinstance(items, (list, tuple)):
                items = raw if isinstance(raw, (list, tuple)) else []
            spaces: list[dict] = []
            for item in items:
                spaces.append(
                    {
                        "id": getattr(item, "space_id", None)
                        or getattr(item, "id", None),
                        "title": getattr(item, "title", None)
                        or getattr(item, "name", None),
                    }
                )
            return spaces
        return None

    def missing_requirements(self) -> list[str]:
        """Human-readable config that must be supplied to authenticate.

        Returns an empty list when enough config is present to *attempt* a real
        connection. This never touches the network; it only inspects config.
        """
        missing: list[str] = []
        # OBO supplies the credential directly via the forwarded user token.
        if self.auth_mode_override == MODE_OBO:
            return missing
        if self.settings.auth_mode == "service_principal":
            if not self.settings.databricks_host:
                missing.append("DATABRICKS_HOST")
            if not self.settings.sp_client_id:
                missing.append("DBX_SP_CLIENT_ID")
            if not self.settings.sp_client_secret:
                missing.append("DBX_SP_CLIENT_SECRET")
            return missing
        # user_workspace mode: a config profile OR host+token is enough.
        if self.settings.databricks_profile:
            return missing
        if not self.settings.databricks_host:
            missing.append("DATABRICKS_HOST")
        if not self.settings.databricks_token:
            missing.append("DATABRICKS_TOKEN")
        return missing

    def connection_status(self) -> dict:
        """Report a structured, secret-free view of the workspace connection.

        Attempts a lightweight ``current_user.me()`` call when a real SDK client
        exists so we can surface the authenticated principal and host. Degrades
        gracefully (``connected=False`` with a clear ``message``) when the SDK is
        unavailable or required config is missing — we never silently proceed.
        """
        missing = self.missing_requirements()
        auth_mode = self.auth_mode_override or self.settings.auth_mode
        # Real interactive OAuth (U2M) is environment-dependent; in headless or
        # mock environments we report what is missing instead of failing hard.
        if self.workspace_client is None:
            if self.auth_mode_override == MODE_OBO:
                if self.init_error:
                    message = (
                        "Received a forwarded user token (OBO) but could not "
                        f"initialize a per-request client: {self.init_error}"
                    )
                else:
                    message = (
                        "Received a forwarded user token (OBO), but the "
                        "Databricks SDK is unavailable to initialize a "
                        "per-request client."
                    )
            elif WorkspaceClient is None:
                message = "Databricks SDK not available; running in mock mode."
            elif missing:
                message = (
                    "Not connected. Missing configuration: " + ", ".join(missing)
                )
            else:
                message = "Not connected. Could not initialize a workspace client."
            return {
                "connected": False,
                "host": self.settings.databricks_host or None,
                "principal": self.principal_override,
                "auth_mode": auth_mode,
                "missing": missing,
                "message": message,
            }

        principal: str | None = self.principal_override
        connected = True
        message = (
            "Connected to Databricks workspace as the signed-in user (OBO)."
            if self.auth_mode_override == MODE_OBO
            else "Connected to Databricks workspace."
        )
        try:
            me = self.workspace_client.current_user.me()  # type: ignore[attr-defined]
            principal = (
                getattr(me, "user_name", None)
                or getattr(me, "display_name", None)
                or principal
            )
        except Exception as exc:  # pragma: no cover - depends on live workspace
            log.error("databricks_whoami_failed", error=str(exc))
            connected = False
            message = (
                "Workspace client initialized but identity check failed: "
                f"{exc}"
            )
        return {
            "connected": connected,
            "host": self.settings.databricks_host or None,
            "principal": principal,
            "auth_mode": auth_mode,
            "missing": missing,
            "message": message,
        }
