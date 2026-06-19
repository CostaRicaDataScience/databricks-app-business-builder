"""Typed configuration provider (implements the ConfigProvider contract)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class MissingConfig(Exception):
    pass


class ConfigProvider:
    def get(self, key: str, default: str | None = None) -> str | None:
        return os.environ.get(key, default)

    def require(self, key: str) -> str:
        value = os.environ.get(key)
        if value is None:
            raise MissingConfig(f'Missing required config: {key}')
        return value

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = os.environ.get(key)
        if value is None:
            return default
        return value.lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class AppSettings:
    databricks_host: str
    databricks_token: str | None
    auth_mode: str
    service_principal_client_id: str | None
    service_principal_client_secret: str | None
    foundation_model_provider: str
    preferred_model: str
    fallback_model: str
    output_root: str
    # MCP integration (disabled by default).
    mcp_server_url: str | None = None
    mcp_genie_space_ids: tuple[str, ...] = ()
    mcp_uc_schema: str | None = None
    # Phase B build-out planner endpoint (Claude Opus by default), distinct from
    # the codegen endpoint. Overridable via PLANNER_MODEL_ENDPOINT.
    planner_model_endpoint: str = "databricks-claude-opus-4"


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def load_settings(provider: ConfigProvider | None = None) -> AppSettings:
    cfg = provider or config
    return AppSettings(
        databricks_host=cfg.get("DATABRICKS_HOST", "https://example.databricks.com"),
        databricks_token=cfg.get("DATABRICKS_TOKEN"),
        auth_mode=cfg.get("DBX_AUTH_MODE", "user_workspace"),
        service_principal_client_id=cfg.get("DBX_SP_CLIENT_ID"),
        service_principal_client_secret=cfg.get("DBX_SP_CLIENT_SECRET"),
        foundation_model_provider=cfg.get(
            "FOUNDATION_MODEL_PROVIDER", "databricks_foundation_model_apis"
        ),
        planner_model_endpoint=cfg.get(
            "PLANNER_MODEL_ENDPOINT", "databricks-claude-opus-4"
        ),
        preferred_model=cfg.get("PREFERRED_MODEL", "claude"),
        fallback_model=cfg.get("FALLBACK_MODEL", "databricks-gpt-fallback"),
        output_root=cfg.get("OUTPUT_ROOT", "./generated_apps"),
        mcp_server_url=cfg.get("MCP_SERVER_URL") or None,
        mcp_genie_space_ids=_parse_csv(cfg.get("MCP_GENIE_SPACE_IDS")),
        mcp_uc_schema=cfg.get("MCP_UC_SCHEMA") or None,
    )


config = ConfigProvider()
