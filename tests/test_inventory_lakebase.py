"""Tests for Lakebase-aware inventory + create-vs-reuse decisions (Phase 2)."""

from __future__ import annotations

from composer.databricks.inventory import collect_inventory
from composer.models.blueprint import DiscoveryReport, DiscoveryResourceStatus
from composer.models.intake import IntakeSpec


def _intake() -> IntakeSpec:
    return IntakeSpec.model_validate(
        {
            "primary_use_case_description": "chat app",
            "user_stories": ["conversar"],
            "gold_tables": ["cat.schema.gold_x"],
            "existing_genies": [],
            "workflow_requirements": "nightly",
            "style_preferences": "",
            "access_requirements": "directors",
        }
    )


def _discovery() -> DiscoveryReport:
    return DiscoveryReport(
        report_id="r1",
        tables=[DiscoveryResourceStatus(name="cat.schema.gold_x", status="exists")],
        genies=[],
        summary="ok",
    )


class _FakeClient:
    def __init__(self, lakebase: list[str] | None, endpoints: list[str]):
        self._lakebase = lakebase
        self._endpoints = endpoints

    def has_real_client(self) -> bool:
        return True

    def list_resource_names(self, service, method="list", **kwargs):
        if service == "serving_endpoints":
            return self._endpoints
        return []

    def list_lakebase_instances(self):
        return self._lakebase


def test_offline_marks_everything_unverified():
    inv = collect_inventory(
        client=None,
        intake=_intake(),
        discovery=_discovery(),
        serving_endpoint="databricks-claude-sonnet",
        connected=False,
        required_primitives=("serving_endpoint", "lakebase"),
    )
    assert inv["checked"] is False
    lb = [i for i in inv["to_create"] if i["resource_type"] == "lakebase_instance"]
    assert lb and lb[0]["verified"] is False
    assert lb[0]["decision"] == "create"


def test_existing_lakebase_is_reused():
    client = _FakeClient(lakebase=["existing-lb"], endpoints=["databricks-claude-sonnet"])
    inv = collect_inventory(
        client=client,
        intake=_intake(),
        discovery=_discovery(),
        serving_endpoint="databricks-claude-sonnet",
        connected=True,
        required_primitives=("serving_endpoint", "lakebase"),
    )
    assert inv["checked"] is True
    lb = [i for i in inv["to_create"] if i["resource_type"] == "lakebase_instance"]
    assert lb and lb[0]["decision"] == "reuse"
    assert lb[0]["name"] == "existing-lb"
    # serving endpoint exists -> not added to create
    se = [i for i in inv["to_create"] if i["resource_type"] == "serving_endpoint"]
    assert se == []


def test_lakebase_skipped_when_not_required():
    client = _FakeClient(lakebase=[], endpoints=["databricks-claude-sonnet"])
    inv = collect_inventory(
        client=client,
        intake=_intake(),
        discovery=_discovery(),
        serving_endpoint="databricks-claude-sonnet",
        connected=True,
        required_primitives=("uc_tables",),
    )
    assert "lakebase" not in inv["resources"]
    assert all(i["resource_type"] != "lakebase_instance" for i in inv["to_create"])


def test_every_to_create_has_resource_id_and_decision():
    inv = collect_inventory(
        client=None,
        intake=_intake(),
        discovery=_discovery(),
        serving_endpoint="databricks-claude-sonnet",
        connected=False,
        required_primitives=("serving_endpoint",),
    )
    for item in inv["to_create"]:
        assert item.get("resource_id")
        assert item.get("decision") in {"create", "reuse", "skip"}
