"""Propose fixes for validation failures and decide whether to redeploy.

Maps the well-known failures from ``validate_app`` to concrete, human-readable
remediations. Fixes are *proposed* (never auto-applied to a live deploy without
approval); the orchestrator surfaces them and offers redeploy.
"""

from __future__ import annotations

_FIXES = {
    "requirements_sdk": (
        "Add 'databricks-sdk' to requirements.txt and redeploy (OBO needs the SDK)."
    ),
    "app_yaml_command": (
        "Set a valid 'command' (YAML sequence) in app.yaml; remove invalid top-level "
        "name/description fields."
    ),
    "oauth_scopes": (
        "Enable the missing OAuth scopes in the App's user-authorization settings, "
        "then redeploy."
    ),
    "smoke": (
        "The deployed app did not return a healthy status. Check the start command "
        "and app logs, then redeploy."
    ),
    "logs": (
        "Errors found in the app logs. If it is 'more than one authorization method', "
        "build the WorkspaceClient with auth_type='pat'. Fix and redeploy."
    ),
}


def propose_fixes(validation_report: dict) -> list[dict]:
    """Return a list of ``{check, fix}`` for each failed check."""
    fixes: list[dict] = []
    for failure in validation_report.get("failures") or []:
        name = failure.get("name")
        fix = _FIXES.get(name, "Review this check and address the reported detail.")
        fixes.append({"check": name, "detail": failure.get("detail"), "fix": fix})
    return fixes


def should_redeploy(validation_report: dict) -> bool:
    """True when there are actionable failures that a redeploy could resolve."""
    actionable = {"requirements_sdk", "app_yaml_command", "smoke", "logs"}
    return any(
        f.get("name") in actionable for f in (validation_report.get("failures") or [])
    )
