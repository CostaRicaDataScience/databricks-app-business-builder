"""Tests for the local dev preflight (Phase 6) - runner injected, no real CLI."""

from __future__ import annotations

import composer.deploy.local_dev as local_dev
from composer.deploy.local_dev import _parse_profiles, local_dev_preflight


def test_parse_profiles():
    out = (
        "Name        Host                      Valid\n"
        "DEFAULT     https://x.databricks.com  YES\n"
        "old         https://y.databricks.com  NO\n"
    )
    rows = _parse_profiles(out)
    assert {"name": "DEFAULT", "valid": True} in rows
    assert {"name": "old", "valid": False} in rows


def test_preflight_no_cli(monkeypatch):
    monkeypatch.setattr(local_dev.shutil, "which", lambda _: None)
    res = local_dev_preflight(runner=lambda cmd: (0, ""))
    assert res["cli_installed"] is False
    assert res["ready"] is False


def test_preflight_ready_with_valid_profile(monkeypatch):
    monkeypatch.setattr(local_dev.shutil, "which", lambda _: "/usr/bin/databricks")

    def runner(cmd):
        if cmd[:2] == ["databricks", "--version"]:
            return 0, "Databricks CLI v1.0.0\n"
        if cmd[:3] == ["databricks", "auth", "profiles"]:
            return 0, "Name Host Valid\nDEFAULT https://x YES\n"
        if cmd[:3] == ["databricks", "aitools", "version"]:
            return 0, "aitools 1.2.3\n"
        return 1, ""

    res = local_dev_preflight(runner=runner)
    assert res["cli_installed"] is True
    assert res["has_valid_profile"] is True
    assert res["aitools_version"] == "aitools 1.2.3"
    assert res["ready"] is True
