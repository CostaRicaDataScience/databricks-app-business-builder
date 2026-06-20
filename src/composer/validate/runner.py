"""Validate a generated app: static checks + optional deployed smoke/log triage.

Static checks (always available, offline-safe):
- requirements.txt includes the Databricks SDK (OBO needs it).
- app.yaml has a runnable command.
- the required OAuth scopes (from the manifest) are granted by the connection.

Deployed checks (optional; injected for tests):
- ``http_get(url)`` smoke test (expects a 2xx-like status).
- ``logs_reader()`` returns recent app logs; we triage for error markers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from composer.core.logging import log

_ERROR_MARKERS = ("Traceback", "ERROR", "ModuleNotFoundError", "more than one authorization")


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _static_checks(app_dir: Path, required_scopes, granted_scopes) -> list[dict]:
    checks: list[dict] = []

    req = app_dir / "requirements.txt"
    req_text = req.read_text(encoding="utf-8") if req.exists() else ""
    checks.append(
        _check(
            "requirements_sdk",
            "databricks-sdk" in req_text,
            "requirements.txt includes databricks-sdk"
            if "databricks-sdk" in req_text
            else "requirements.txt missing databricks-sdk (OBO needs it)",
        )
    )

    app_yaml = app_dir / "app.yaml"
    command_ok = False
    if app_yaml.exists():
        try:
            data = yaml.safe_load(app_yaml.read_text(encoding="utf-8")) or {}
            command_ok = bool(data.get("command"))
        except Exception:
            command_ok = False
    checks.append(
        _check(
            "app_yaml_command",
            command_ok,
            "app.yaml has a command" if command_ok else "app.yaml missing/invalid command",
        )
    )

    if required_scopes is not None:
        missing = [s for s in required_scopes if s not in set(granted_scopes or [])]
        checks.append(
            _check(
                "oauth_scopes",
                not missing,
                "all required OAuth scopes granted"
                if not missing
                else f"missing OAuth scopes: {', '.join(missing)}",
            )
        )
    return checks


def _deployed_checks(
    app_url: str | None,
    http_get: Callable[[str], int] | None,
    logs_reader: Callable[[], str] | None,
) -> list[dict]:
    checks: list[dict] = []
    if app_url and http_get is not None:
        try:
            status = http_get(app_url)
        except Exception as exc:  # pragma: no cover - injected in tests
            status = -1
            log.info("smoke_failed", url=app_url, error=str(exc))
        checks.append(
            _check(
                "smoke",
                isinstance(status, int) and 200 <= status < 400,
                f"GET {app_url} -> {status}",
            )
        )
    if logs_reader is not None:
        try:
            logs = logs_reader() or ""
        except Exception as exc:  # pragma: no cover - injected in tests
            logs = ""
            log.info("logs_read_failed", error=str(exc))
        hits = [m for m in _ERROR_MARKERS if m in logs]
        checks.append(
            _check(
                "logs",
                not hits,
                "no error markers in logs" if not hits else f"errors in logs: {', '.join(hits)}",
            )
        )
    return checks


def validate_app(
    app_dir: str | Path,
    *,
    required_scopes: list[str] | None = None,
    granted_scopes: list[str] | None = None,
    app_url: str | None = None,
    http_get: Callable[[str], int] | None = None,
    logs_reader: Callable[[], str] | None = None,
) -> dict:
    """Return ``{ok, checks, failures}`` for the generated app."""
    base = Path(app_dir)
    checks = _static_checks(base, required_scopes, granted_scopes)
    checks += _deployed_checks(app_url, http_get, logs_reader)
    failures = [c for c in checks if not c["ok"]]
    return {
        "ok": not failures,
        "checks": checks,
        "failures": failures,
    }
