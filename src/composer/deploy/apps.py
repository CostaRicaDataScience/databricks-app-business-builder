"""Deployment facade for Databricks Apps API / DAB flows."""

from __future__ import annotations


def deploy_app(app_path: str, dry_run: bool = True) -> dict:
    if dry_run:
        return {"status": "planned", "app_path": app_path, "provider": "apps_api_or_dab"}
    return {"status": "deployed", "app_path": app_path, "provider": "apps_api_or_dab"}
