"""Tests for the validation runner (Phase 5)."""

from __future__ import annotations

from pathlib import Path

from composer.validate import validate_app


def _make_app(tmp_path: Path, *, sdk=True, command=True) -> Path:
    app = tmp_path / "app"
    app.mkdir()
    req = "fastapi\n" + ("databricks-sdk\n" if sdk else "")
    (app / "requirements.txt").write_text(req, encoding="utf-8")
    if command:
        (app / "app.yaml").write_text("command:\n  - uvicorn\n", encoding="utf-8")
    else:
        (app / "app.yaml").write_text("name: x\n", encoding="utf-8")
    return app


def test_static_checks_pass(tmp_path):
    app = _make_app(tmp_path)
    report = validate_app(app)
    assert report["ok"] is True
    names = {c["name"] for c in report["checks"]}
    assert {"requirements_sdk", "app_yaml_command"} <= names


def test_missing_sdk_and_command_fail(tmp_path):
    app = _make_app(tmp_path, sdk=False, command=False)
    report = validate_app(app)
    assert report["ok"] is False
    failed = {f["name"] for f in report["failures"]}
    assert "requirements_sdk" in failed
    assert "app_yaml_command" in failed


def test_scopes_check(tmp_path):
    app = _make_app(tmp_path)
    report = validate_app(
        app, required_scopes=["sql", "dashboards.genie"], granted_scopes=["sql"]
    )
    scope_check = next(c for c in report["checks"] if c["name"] == "oauth_scopes")
    assert scope_check["ok"] is False
    assert "dashboards.genie" in scope_check["detail"]


def test_deployed_smoke_and_logs(tmp_path):
    app = _make_app(tmp_path)
    report = validate_app(
        app,
        app_url="https://app.example.com",
        http_get=lambda url: 200,
        logs_reader=lambda: "all good\n",
    )
    assert report["ok"] is True


def test_log_triage_flags_obo_error(tmp_path):
    app = _make_app(tmp_path)
    report = validate_app(
        app,
        logs_reader=lambda: "ERROR: more than one authorization method configured",
    )
    logs_check = next(c for c in report["checks"] if c["name"] == "logs")
    assert logs_check["ok"] is False
