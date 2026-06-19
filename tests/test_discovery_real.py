"""Tests for honest, workspace-verified discovery and Genie search intent."""

from __future__ import annotations

from composer.discovery.service import DiscoveryService
from composer.genie.resolver import is_search_request
from composer.models.intake import IntakeSpec


class _FakeWorkspace:
    """Stand-in for composer DatabricksClient with controllable answers."""

    def __init__(self, tables: dict, genie_spaces):
        self._tables = tables
        self._genie_spaces = genie_spaces

    def has_real_client(self) -> bool:
        return True

    def inspect_table(self, full_name: str):
        # A live client always returns a dict; "not found" is exists=False
        # (mirrors composer.databricks.client.DatabricksClient.inspect_table).
        return self._tables.get(
            full_name,
            {"exists": False, "has_description": False, "missing_columns": []},
        )

    def search_genie_spaces(self):
        return self._genie_spaces


def _intake(genies):
    return IntakeSpec(
        primary_use_case_description="App para el director",
        user_stories=["Presentar info de investigación y estudiantes"],
        gold_tables=["uc.gold.estudiante_360", "uc.gold.research_cockpit"],
        existing_genies=genies,
        workflow_requirements="Cada noche",
        style_preferences="glass iOS 2026",
        access_requirements="Los directores",
    )


def test_search_intent_detection():
    assert is_search_request("No estoy seguro, quiero que busques")
    assert is_search_request("busca uno por mí")
    assert is_search_request("not sure, find one")
    assert not is_search_request("sales_assistant")
    assert not is_search_request("estudiante_360_genie")


def test_tables_verified_against_workspace():
    ws = _FakeWorkspace(
        tables={
            "uc.gold.estudiante_360": {
                "exists": True,
                "has_description": True,
                "missing_columns": [],
            },
            "uc.gold.research_cockpit": {
                "exists": True,
                "has_description": False,
                "missing_columns": ["kpi"],
            },
        },
        genie_spaces=[],
    )
    report = DiscoveryService(workspace=ws).run(_intake([]))
    statuses = {t.name: t.status for t in report.tables}
    assert statuses["uc.gold.estudiante_360"] == "exists"
    assert statuses["uc.gold.research_cockpit"] == "needs_enrichment"
    assert "workspace" in report.summary.lower()


def test_missing_table_reported():
    ws = _FakeWorkspace(
        tables={
            "uc.gold.estudiante_360": {
                "exists": False,
                "has_description": False,
                "missing_columns": [],
            }
        },
        genie_spaces=[],
    )
    report = DiscoveryService(workspace=ws).run(_intake([]))
    statuses = {t.name: t.status for t in report.tables}
    assert statuses["uc.gold.estudiante_360"] == "missing"
    # Not configured in the fake -> live client returns exists=False -> missing.
    assert statuses["uc.gold.research_cockpit"] == "missing"


def test_genie_search_finds_existing_space():
    ws = _FakeWorkspace(
        tables={},
        genie_spaces=[{"id": "1", "title": "student_assistant"}],
    )
    report = DiscoveryService(workspace=ws).run(
        _intake(["No estoy seguro, quiero que busques"])
    )
    genie_names = {g.name: g.status for g in report.genies}
    assert "student_assistant" in genie_names
    assert genie_names["student_assistant"] == "exists"


def test_genie_search_recommends_creation_when_none_found():
    ws = _FakeWorkspace(tables={}, genie_spaces=[])
    report = DiscoveryService(workspace=ws).run(
        _intake(["no estoy seguro, busca"])
    )
    statuses = [g.status for g in report.genies]
    assert "needs_creation" in statuses


def test_genie_search_without_connection_is_unknown():
    # No workspace -> we cannot search -> honest unknown, not a fake name.
    report = DiscoveryService(workspace=None).run(
        _intake(["No estoy seguro, quiero que busques"])
    )
    statuses = [g.status for g in report.genies]
    assert statuses == ["unknown"]
