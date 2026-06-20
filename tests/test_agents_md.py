"""Tests for AGENTS.md authoring + design system (Phase 3)."""

from __future__ import annotations

from composer.codegen.agents_md import build_agents_md
from composer.codegen.design_system import PALETTE, css_tokens, design_system_markdown


def _manifest() -> dict:
    return {
        "project": {"name": "demo-app"},
        "archetype": {
            "id": "genie_analytics",
            "title": "Genie Analytics App",
            "target": "python",
            "devhub_url": "https://developers.databricks.com/templates/genie-analytics-app",
        },
        "intake": {
            "primary_use_case_description": "App para directores",
            "user_stories": ["revisar numeros"],
            "gold_tables": ["cat.gold.students", "cat.gold.research"],
        },
        "runtime": {
            "databricks_apps": {
                "obo_header": "x-forwarded-access-token",
                "required_oauth_scopes": ["sql", "dashboards.genie"],
                "system_env": ["DATABRICKS_HOST"],
            }
        },
        "references": {
            "serving_endpoints": {"codegen": "databricks-claude-sonnet", "planner": "databricks-claude-opus-4"},
            "genie_spaces": ["space-1"],
        },
    }


def test_agents_md_contains_workspace_defaults_and_palette():
    md = build_agents_md(_manifest())
    assert "Genie Analytics App" in md
    assert "developers.databricks.com/templates/genie-analytics-app" in md
    assert "cat.gold" in md  # catalog.schema derived
    assert "dashboards.genie" in md
    assert "x-forwarded-access-token" in md
    assert "auth_type='pat'" in md
    assert PALETTE["primary"] in md


def test_design_system_markdown_targets():
    py = design_system_markdown("python")
    appkit = design_system_markdown("appkit")
    assert "css" in py.lower()
    assert "shadcn" in appkit.lower()
    assert PALETTE["background"] in css_tokens()
