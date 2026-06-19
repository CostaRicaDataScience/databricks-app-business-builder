"""Databricks SDK client wrapper with safe fallback mode."""

from __future__ import annotations

from dataclasses import dataclass

from composer.core.config import Settings
from composer.core.logging import log

try:
    from databricks.sdk import WorkspaceClient  # type: ignore
except Exception:  # pragma: no cover
    WorkspaceClient = None  # type: ignore


@dataclass(slots=True)
class DatabricksClient:
    settings: Settings
    workspace_client: object | None

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

    def missing_requirements(self) -> list[str]:
        """Human-readable config that must be supplied to authenticate.

        Returns an empty list when enough config is present to *attempt* a real
        connection. This never touches the network; it only inspects config.
        """
        missing: list[str] = []
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
        # Real interactive OAuth (U2M) is environment-dependent; in headless or
        # mock environments we report what is missing instead of failing hard.
        if self.workspace_client is None:
            if WorkspaceClient is None:
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
                "principal": None,
                "auth_mode": self.settings.auth_mode,
                "missing": missing,
                "message": message,
            }

        principal: str | None = None
        connected = True
        message = "Connected to Databricks workspace."
        try:
            me = self.workspace_client.current_user.me()  # type: ignore[attr-defined]
            principal = getattr(me, "user_name", None) or getattr(me, "display_name", None)
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
            "auth_mode": self.settings.auth_mode,
            "missing": missing,
            "message": message,
        }
