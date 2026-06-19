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


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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
        preferred_model=os.getenv("PREFERRED_MODEL", "claude"),
        fallback_model=os.getenv("FALLBACK_MODEL", "databricks-gpt-fallback"),
        appgen_dir=os.getenv("APPGEN_DIR", ".appgen"),
        output_root=os.getenv("OUTPUT_ROOT", "./generated_apps"),
        dry_run_default=_env_bool("DRY_RUN_DEFAULT", True),
    )
