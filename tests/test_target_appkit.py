"""Tests for the AppKit target plan (Phase 4) - runner mocked, no real CLI."""

from __future__ import annotations

from composer.archetypes import get_archetype
from composer.codegen.targets.appkit_target import build_appkit_target, plugins_for
from composer.models.intake import IntakeSpec


def _intake() -> IntakeSpec:
    return IntakeSpec.model_validate(
        {
            "primary_use_case_description": "chat",
            "user_stories": ["conversar"],
            "gold_tables": ["c.s.t"],
            "existing_genies": [],
            "workflow_requirements": "",
            "style_preferences": "",
            "access_requirements": "",
        }
    )


def test_plugins_mapped_from_primitives():
    arch = get_archetype("ai_chat")  # serving_endpoint + lakebase (+ genie optional)
    plugins = plugins_for(arch)
    assert "model-serving" in plugins
    assert "lakebase" in plugins


def test_disabled_returns_plan_without_executing():
    arch = get_archetype("ai_chat")
    calls = {"n": 0}

    def runner(cmd):  # pragma: no cover - must not run when disabled
        calls["n"] += 1

    plan = build_appkit_target(
        arch, _intake(), app_dir="/tmp/x", enabled=False, runner=runner
    )
    assert plan["executed"] is False
    assert plan["reason"] == "feature_flag_off"
    assert calls["n"] == 0
    assert plan["command"][:3] == ["databricks", "apps", "init"]


def test_enabled_executes_via_injected_runner(monkeypatch):
    arch = get_archetype("crud_lakebase")
    monkeypatch.setattr(
        "composer.codegen.targets.appkit_target.appkit_available", lambda: True
    )
    captured = {}

    def runner(cmd):
        captured["cmd"] = cmd

    plan = build_appkit_target(
        arch, _intake(), app_dir="/tmp/x", enabled=True, runner=runner
    )
    assert plan["executed"] is True
    assert captured["cmd"][:3] == ["databricks", "apps", "init"]
    assert "lakebase" in captured["cmd"]
