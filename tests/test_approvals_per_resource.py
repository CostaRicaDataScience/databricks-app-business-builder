"""Tests for per-resource approval decisions (Phase 2)."""

from __future__ import annotations

import pytest

from composer.core.approvals import ApprovalGate


def _gate(tmp_path) -> ApprovalGate:
    return ApprovalGate(root=str(tmp_path), dry_run=True)


def test_default_decision_is_item_default(tmp_path):
    gate = _gate(tmp_path)
    plan = [
        {"resource_type": "lakebase_instance", "name": "lb", "resource_id": "lakebase_instance:lb", "decision": "reuse"},
        {"resource_type": "databricks_app", "name": "app", "resource_id": "databricks_app:app", "decision": "create"},
    ]
    applied = gate.apply_decisions(plan)
    decisions = {i["resource_id"]: i["decision"] for i in applied}
    assert decisions["lakebase_instance:lb"] == "reuse"
    assert decisions["databricks_app:app"] == "create"


def test_skip_filters_resource(tmp_path):
    gate = _gate(tmp_path)
    gate.set_decision("genie_space:g1", "skip")
    plan = [
        {"resource_type": "genie_space", "name": "g1", "resource_id": "genie_space:g1", "decision": "create"},
        {"resource_type": "databricks_app", "name": "app", "resource_id": "databricks_app:app", "decision": "create"},
    ]
    applied = gate.apply_decisions(plan)
    ids = {i["resource_id"] for i in applied}
    assert "genie_space:g1" not in ids
    assert "databricks_app:app" in ids


def test_user_override_create_to_reuse(tmp_path):
    gate = _gate(tmp_path)
    gate.set_decision("serving_endpoint:ep", "reuse")
    plan = [{"resource_type": "serving_endpoint", "name": "ep", "resource_id": "serving_endpoint:ep", "decision": "create"}]
    applied = gate.apply_decisions(plan)
    assert applied[0]["decision"] == "reuse"


def test_invalid_decision_raises(tmp_path):
    gate = _gate(tmp_path)
    with pytest.raises(ValueError):
        gate.set_decision("x", "maybe")


def test_resource_id_derived_when_missing(tmp_path):
    gate = _gate(tmp_path)
    plan = [{"resource_type": "databricks_app", "name": "app", "decision": "create"}]
    applied = gate.apply_decisions(plan)
    assert applied[0]["decision"] == "create"
