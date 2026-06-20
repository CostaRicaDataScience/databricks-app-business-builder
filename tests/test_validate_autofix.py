"""Tests for validation autofix proposals (Phase 5)."""

from __future__ import annotations

from composer.validate import propose_fixes, should_redeploy


def _report(*failed_names) -> dict:
    failures = [{"name": n, "detail": f"{n} failed"} for n in failed_names]
    return {"ok": not failures, "checks": failures, "failures": failures}


def test_propose_fixes_maps_known_checks():
    fixes = propose_fixes(_report("requirements_sdk", "oauth_scopes"))
    by_check = {f["check"]: f["fix"] for f in fixes}
    assert "databricks-sdk" in by_check["requirements_sdk"]
    assert "OAuth scopes" in by_check["oauth_scopes"]


def test_should_redeploy_for_actionable_failures():
    assert should_redeploy(_report("requirements_sdk")) is True
    assert should_redeploy(_report("logs")) is True


def test_should_not_redeploy_for_scopes_only():
    # scopes are fixed in app settings, not by a redeploy alone
    assert should_redeploy(_report("oauth_scopes")) is False


def test_no_failures_no_fixes():
    assert propose_fixes(_report()) == []
    assert should_redeploy(_report()) is False
