"""Databricks connection & permission status service.

This is the single place the app uses to answer "are we connected to the user's
Databricks workspace, as whom, and which permissions are we about to request?".

It bridges the compatibility ``AppSettings`` to the composer ``Settings`` and
uses the real Databricks SDK via ``composer.databricks.client.DatabricksClient``.
Real interactive OAuth (U2M) is environment-dependent; when the SDK cannot
establish a client (no token/host/profile, or headless env) we report exactly
what is missing instead of silently proceeding. No secrets are ever returned.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))

from composer.core.config import Settings as ComposerSettings
from composer.databricks.client import DatabricksClient
from composer.databricks.obo import RequestAuth
from composer.permissions.preflight import (
    DEFAULT_REQUIRED_CAPABILITIES,
    summarize_permissions,
)
from modules.core.config import AppSettings


def _to_composer_settings(settings: AppSettings) -> ComposerSettings:
    return ComposerSettings(
        databricks_host=settings.databricks_host,
        databricks_token=settings.databricks_token,
        databricks_profile=os.getenv("DATABRICKS_CONFIG_PROFILE"),
        auth_mode=settings.auth_mode,
        sp_client_id=settings.service_principal_client_id,
        sp_client_secret=settings.service_principal_client_secret,
        foundation_model_endpoint=os.getenv(
            "FOUNDATION_MODEL_ENDPOINT", "databricks-claude-sonnet"
        ),
        planner_model_endpoint=settings.planner_model_endpoint,
        preferred_model=settings.preferred_model,
        fallback_model=settings.fallback_model,
        appgen_dir=os.getenv("APPGEN_DIR", ".appgen"),
        output_root=settings.output_root,
        dry_run_default=True,
        mcp_server_url=settings.mcp_server_url,
        mcp_genie_space_ids=settings.mcp_genie_space_ids,
        mcp_uc_schema=settings.mcp_uc_schema,
    )


class DatabricksConnectionService:
    """Resolve and report Databricks connection + permission status."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._composer_settings = _to_composer_settings(settings)

    @property
    def composer_settings(self) -> ComposerSettings:
        return self._composer_settings

    def _client(self, auth: RequestAuth | None = None) -> DatabricksClient:
        if auth is not None and auth.is_obo:
            return DatabricksClient.for_request(self._composer_settings, auth)
        return DatabricksClient.from_settings(self._composer_settings)

    def workspace_client(self, auth: RequestAuth | None = None) -> object | None:
        """Return the underlying SDK ``WorkspaceClient`` for this request (or None).

        Uses the forwarded OBO user token when present so downstream calls run
        as the signed-in user; otherwise falls back to configured credentials.
        """
        return self._client(auth).workspace_client

    def databricks_client(self, auth: RequestAuth | None = None) -> DatabricksClient:
        """Return the composer ``DatabricksClient`` wrapper for this request.

        Exposes higher-level, honest helpers (``inspect_table``,
        ``search_genie_spaces``) used by discovery to verify resources against
        the live workspace as the signed-in user.
        """
        return self._client(auth)

    def capabilities(self, credentials_present: bool) -> dict[str, bool]:
        """Permissions we believe are available given current credentials.

        Until a live workspace ACL/entitlement check is wired, capability
        availability tracks whether the user supplied usable credentials. This
        keeps the preflight honest: no credentials -> nothing is satisfied.
        """
        return {key: credentials_present for key in DEFAULT_REQUIRED_CAPABILITIES}

    def status(self, auth: RequestAuth | None = None) -> dict:
        client = self._client(auth)
        conn = client.connection_status()
        credentials_present = not conn["missing"]
        capabilities = self.capabilities(
            credentials_present=credentials_present or conn["connected"]
        )
        return {
            "connected": conn["connected"],
            "host": conn["host"],
            "principal": conn["principal"],
            "auth_mode": conn["auth_mode"],
            "missing": conn["missing"],
            "message": conn["message"],
            "credentials_present": credentials_present,
            "sdk_available": client.has_real_client(),
            "permissions": summarize_permissions(capabilities),
        }
