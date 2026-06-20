"""Tests for the archetype catalog + intake classifier (Phase 1)."""

from __future__ import annotations

from composer.archetypes import (
    classify_intake,
    default_archetype,
    get_archetype,
    list_archetypes,
)
from composer.archetypes.catalog import TARGET_APPKIT, TARGET_PYTHON
from composer.models.intake import IntakeSpec


def _intake(**overrides) -> IntakeSpec:
    payload = {
        "primary_use_case_description": "",
        "user_stories": [],
        "gold_tables": ["cat.schema.gold_x"],
        "existing_genies": [],
        "workflow_requirements": "nightly",
        "style_preferences": "",
        "access_requirements": "directors",
    }
    payload.update(overrides)
    return IntakeSpec.model_validate(payload)


def test_catalog_has_expected_archetypes():
    ids = {a.id for a in list_archetypes()}
    assert {"ai_chat", "crud_lakebase", "genie_analytics", "rag_chat", "dashboard"} <= ids
    assert get_archetype("ai_chat").devhub_url.startswith("https://developers.databricks.com")
    assert get_archetype("nope") is None


def test_genie_reference_routes_to_genie_analytics():
    intake = _intake(
        primary_use_case_description="App para directores con un Genie embebido",
        existing_genies=["serverless.gold.estudiante_360_genie"],
        user_stories=["conversar con los datos"],
    )
    result = classify_intake(intake)
    assert result.archetype_id == "genie_analytics"
    assert result.needs_help is False
    assert result.target == TARGET_PYTHON  # archetype default


def test_chat_intent_routes_to_ai_chat():
    intake = _intake(
        primary_use_case_description="Quiero un chatbot para conversar y preguntar",
        user_stories=["enviar un mensaje y recibir respuesta en streaming"],
    )
    result = classify_intake(intake)
    assert result.archetype_id == "ai_chat"


def test_dashboard_intent():
    intake = _intake(
        primary_use_case_description="Tablero de KPIs y metricas para ver avances",
        user_stories=["visualizar numeros semanales"],
    )
    result = classify_intake(intake)
    assert result.archetype_id == "dashboard"


def test_weak_signal_falls_back_to_default_with_help():
    intake = _intake(
        primary_use_case_description="algo",
        user_stories=[],
        workflow_requirements="",
        access_requirements="",
    )
    result = classify_intake(intake)
    assert result.archetype_id == default_archetype().id
    assert result.needs_help is True


def test_target_hint_overrides_default():
    intake = _intake(
        primary_use_case_description="Un chatbot en typescript con react",
        user_stories=["conversar"],
    )
    result = classify_intake(intake)
    assert result.target == TARGET_APPKIT
