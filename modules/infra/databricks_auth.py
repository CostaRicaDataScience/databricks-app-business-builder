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
        preferred_model=settings.preferred_model,
        fallback_model=settings.fallback_model,
        appgen_dir=os.getenv("APPGEN_DIR", ".appgen"),
        output_root=settings.output_root,
        dry_run_default=True,
    )


class DatabricksConnectionService:
    """Resolve and report Databricks connection + permission status."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._composer_settings = _to_composer_settings(settings)

    def _client(self) -> DatabricksClient:
        return DatabricksClient.from_settings(self._composer_settings)

    def capabilities(self, credentials_present: bool) -> dict[str, bool]:
        """Permissions we believe are available given current credentials.

        Until a live workspace ACL/entitlement check is wired, capability
        availability tracks whether the user supplied usable credentials. This
        keeps the preflight honest: no credentials -> nothing is satisfied.
        """
        return {key: credentials_present for key in DEFAULT_REQUIRED_CAPABILITIES}

    def status(self) -> dict:
        client = self._client()
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
