"""Tests for the Python target plan (Phase 4)."""

from __future__ import annotations

from composer.archetypes import get_archetype
from composer.codegen.targets import build_python_target
from composer.models.intake import IntakeSpec


def _intake() -> IntakeSpec:
    return IntakeSpec.model_validate(
        {
            "primary_use_case_description": "dashboard",
            "user_stories": ["ver kpis"],
            "gold_tables": ["c.s.t"],
            "existing_genies": [],
            "workflow_requirements": "",
            "style_preferences": "",
            "access_requirements": "",
        }
    )


def test_python_target_includes_styles_and_pages():
    arch = get_archetype("dashboard")
    plan = build_python_target(arch, _intake())
    assert plan["target"] == "python"
    assert "app/styles.css" in plan["extra_files"]
    assert "--dbx-primary" in plan["extra_files"]["app/styles.css"]
    assert plan["pages"]


def test_python_target_flags_from_primitives():
    arch = get_archetype("ai_chat")
    plan = build_python_target(arch, _intake())
    assert plan["needs_serving"] is True
    assert plan["needs_lakebase"] is True
