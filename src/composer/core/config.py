"""Typed settings for composer runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    databricks_host: str
    databricks_token: str | None
    databricks_profile: str | None
    auth_mode: str
    sp_client_id: str | None
    sp_client_secret: str | None
    foundation_model_endpoint: str
    preferred_model: str
    fallback_model: str
    appgen_dir: str
    output_root: str
    dry_run_default: bool
    # MCP integration (disabled by default -> empty/None keeps existing behavior).
    mcp_server_url: str | None = None
    mcp_genie_space_ids: tuple[str, ...] = ()
    mcp_uc_schema: str | None = None
    # Separate, overridable planner endpoint used for the Phase B build-out
    # (Claude Opus by default). Kept distinct from the codegen endpoint above so
    # the deterministic scaffold (Phase A) and the heavy build-out (Phase B) can
    # target different models/governance scopes.
    planner_model_endpoint: str = "databricks-claude-opus-4"


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def parse_csv_env(value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated env value into a tuple, dropping blanks."""
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def load_settings() -> Settings:
    return Settings(
        databricks_host=os.getenv("DATABRICKS_HOST", "https://example.databricks.com"),
        databricks_token=os.getenv("DATABRICKS_TOKEN"),
        databricks_profile=os.getenv("DATABRICKS_CONFIG_PROFILE"),
        auth_mode=os.getenv("DBX_AUTH_MODE", "user_workspace"),
        sp_client_id=os.getenv("DBX_SP_CLIENT_ID"),
        sp_client_secret=os.getenv("DBX_SP_CLIENT_SECRET"),
        foundation_model_endpoint=os.getenv(
            "FOUNDATION_MODEL_ENDPOINT", "databricks-claude-sonnet"
        ),
        planner_model_endpoint=os.getenv(
            "PLANNER_MODEL_ENDPOINT", "databricks-claude-opus-4"
        ),
        preferred_model=os.getenv("PREFERRED_MODEL", "claude"),
        fallback_model=os.getenv("FALLBACK_MODEL", "databricks-gpt-fallback"),
        appgen_dir=os.getenv("APPGEN_DIR", ".appgen"),
        output_root=os.getenv("OUTPUT_ROOT", "./generated_apps"),
        dry_run_default=_env_bool("DRY_RUN_DEFAULT", True),
        mcp_server_url=os.getenv("MCP_SERVER_URL") or None,
        mcp_genie_space_ids=parse_csv_env(os.getenv("MCP_GENIE_SPACE_IDS")),
        mcp_uc_schema=os.getenv("MCP_UC_SCHEMA") or None,
    )
