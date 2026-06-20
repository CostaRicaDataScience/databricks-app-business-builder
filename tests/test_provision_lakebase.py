"""Tests for Lakebase provisioning plan + gates (Phase 4)."""

from __future__ import annotations

from composer.provision.lakebase import plan_lakebase_steps, provision_lakebase


def test_plan_steps_with_chat_memory():
    steps = plan_lakebase_steps("lb", with_chat_memory=True)
    assert any("chat" in s for s in steps)
    assert any("Create Lakebase instance 'lb'" in s for s in steps)


def test_not_approved_is_blocked():
    res = provision_lakebase(None, "lb", approved=False)
    assert res["status"] == "blocked_needs_approval"


def test_approved_dry_run_is_planned_only():
    res = provision_lakebase(None, "lb", approved=True, dry_run=True)
    assert res["status"] == "planned"


def test_approved_real_without_client_is_skipped():
    res = provision_lakebase(None, "lb", approved=True, dry_run=False)
    assert res["status"] == "skipped_no_client"
