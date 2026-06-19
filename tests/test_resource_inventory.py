"""Tests for workspace resource inventory (GET) and the POST creation plan."""

from __future__ import annotations

from composer.databricks.inventory import collect_inventory
from composer.models.blueprint import DiscoveryReport, DiscoveryResourceStatus
from composer.models.intake import IntakeSpec


def _intake() -> IntakeSpec:
    return IntakeSpec(
        primary_use_case_description="App para el director",
        user_stories=["Presentar info"],
        gold_tables=["cat.gold.estudiantes", "cat.gold.research"],
        existing_genies=[],
        workflow_requirements="cada noche",
        style_preferences="glass",
        access_requirements="directores",
    )


def _discovery(table_status="exists", genie_status="needs_creation") -> DiscoveryReport:
    return DiscoveryReport(
        report_id="r1",
        tables=[
            DiscoveryResourceStatus(name="cat.gold.estudiantes", status=table_status),
            DiscoveryResourceStatus(name="cat.gold.research", status="missing"),
        ],
        genies=[
            DiscoveryResourceStatus(name="director_genie", status=genie_status),
        ],
        summary="ok",
    )


class _FakeClient:
    def __init__(self, listings: dict):
        self._listings = listings

    def has_real_client(self) -> bool:
        return True

    def list_resource_names(self, service, method="list", **kwargs):
        return self._listings.get(service)


def test_inventory_not_connected_marks_unverified_and_plans_posts():
    inv = collect_inventory(
        client=None,
        intake=_intake(),
        discovery=_discovery(table_status="unknown"),
        serving_endpoint="databricks-claude-sonnet",
        connected=False,
    )
    assert inv["checked"] is False
    assert inv["resources"]["serving_endpoints"]["checked"] is False
    types = {c["resource_type"] for c in inv["to_create"]}
    # Even offline we plan the model endpoint, the genie, and the app itself.
    assert {"serving_endpoint", "genie_space", "databricks_app"} <= types
    # Offline plans are flagged as pending verification.
    assert all(c["verified"] is False for c in inv["to_create"])


def test_inventory_connected_reads_resources_and_maps_creation():
    client = _FakeClient(
        {
            "serving_endpoints": ["some-other-endpoint"],
            "volumes": ["landing_volume"],
            "knowledge_assistants": [],
            "environments": ["dev", "prod"],
        }
    )
    inv = collect_inventory(
        client=client,
        intake=_intake(),
        discovery=_discovery(),
        serving_endpoint="databricks-claude-sonnet",
        connected=True,
    )
    assert inv["checked"] is True
    assert inv["resources"]["serving_endpoints"]["checked"] is True
    assert "landing_volume" in inv["resources"]["volumes"]["existing"]
    assert inv["resources"]["environments"]["existing"] == ["dev", "prod"]

    types = {c["resource_type"] for c in inv["to_create"]}
    # Configured model endpoint is absent -> must be created.
    assert "serving_endpoint" in types
    assert "genie_space" in types
    assert "databricks_app" in types
    # The missing gold table is reported as a blocker, not silently ignored.
    assert any("research" in b for b in inv["blockers"])


def test_inventory_existing_endpoint_not_replanned():
    client = _FakeClient(
        {
            "serving_endpoints": ["databricks-claude-sonnet"],
            "volumes": [],
            "knowledge_assistants": [],
            "environments": [],
        }
    )
    inv = collect_inventory(
        client=client,
        intake=_intake(),
        discovery=_discovery(genie_status="exists"),
        serving_endpoint="databricks-claude-sonnet",
        connected=True,
    )
    types = [c["resource_type"] for c in inv["to_create"]]
    # Endpoint exists -> not planned; genie exists -> not planned.
    assert "serving_endpoint" not in types
    assert "genie_space" not in types
    # The app itself is still a create.
    assert "databricks_app" in types
