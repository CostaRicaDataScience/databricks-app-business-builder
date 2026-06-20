"""Tests for Genie embedding plan + snippet (Phase 4)."""

from __future__ import annotations

from composer.genie.embed import build_genie_embed_plan, genie_panel_snippet


def test_embed_plan_reuse_and_create():
    plan = build_genie_embed_plan(
        ["existing-space"], "App para directores", to_create=["new-genie"]
    )
    assert plan["reuse"] == ["existing-space"]
    assert plan["embed"] is True
    assert plan["create"][0]["genie_name"] == "new-genie"
    assert plan["create"][0]["status"] == "planned"


def test_embed_plan_empty():
    plan = build_genie_embed_plan([], "x")
    assert plan["embed"] is False


def test_panel_snippet_uses_obo_pat_and_genie_api():
    snippet = genie_panel_snippet("space-123")
    assert "auth_type='pat'" in snippet
    assert "space-123" in snippet
    assert "genie" in snippet
