"""API tests for the guided auto-run flow and auth status endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from modules.app.main import app

client = TestClient(app)


def _intake_payload() -> dict:
    return {
        "primary_use_case_description": "Comparar ventas por región",
        "user_stories": ["Como analista quiero ver KPIs"],
        "gold_tables": ["sales.gold_orders", "sales.gold_customers"],
        "existing_genies": ["sales_assistant", "new_sales_genie"],
        "workflow_requirements": "Se actualiza cada día; mi líder aprueba cambios.",
        "style_preferences": "Tema oscuro, simple.",
        "access_requirements": "El equipo de ventas; lee pedidos y clientes.",
    }


def test_health_still_works():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_home_serves_guided_ui_without_raw_id_headline():
    res = client.get("/")
    assert res.status_code == 200
    body = res.text
    # Guided, plain-language UI markers.
    assert "Conectar a Databricks" in body
    assert "Crear mi app" in body
    # The old jargon labels should be gone.
    assert "Requerimientos de flujo" not in body
    assert "Requerimientos de acceso base" not in body
    # No "next step: POST ... with that intake_id" as the headline UX.
    assert "Siguiente paso: POST /discovery-run" not in body


def test_auth_status_reports_connection_and_permissions():
    res = client.get("/auth/status")
    assert res.status_code == 200
    data = res.json()
    for key in ("connected", "auth_mode", "message", "permissions", "missing"):
        assert key in data
    assert isinstance(data["permissions"], list)
    assert data["permissions"], "should list requested permissions"
    perm = data["permissions"][0]
    assert {"key", "label", "why", "satisfied"} <= set(perm)


def test_auth_connect_returns_status_shape():
    res = client.post("/auth/connect")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert "permissions" in data


def test_run_pipeline_returns_human_friendly_summary():
    res = client.post("/run", json=_intake_payload())
    assert res.status_code == 200
    s = res.json()
    # Human-readable headline, not a raw UUID.
    assert s["headline"]
    # Named progress steps.
    step_keys = {step["key"] for step in s["steps"]}
    assert {"intake", "connect", "discovery", "autofix", "generate"} <= step_keys
    # Discovery surfaced in plain terms. Without a live workspace connection in
    # tests, tables are honestly reported as unverified (never faked as found).
    assert "sales.gold_orders" in s["data"]["tables_unverified"]
    assert "sales.gold_customers" in s["data"]["tables_unverified"]
    # Existing vs to-create assistants.
    assert "sales_assistant" in s["assistants"]["existing"]
    assert "new_sales_genie" in s["assistants"]["to_create"]
    # Sensitive actions require approval, not auto-executed.
    assert any("new_sales_genie" in r for r in s["requires_approval"])
    # Generated app reported with a path.
    assert s["generated_app"]["output_path"]
    # IDs exist but only as secondary/debug detail.
    assert set(s["ids"]) == {"intake_id", "report_id", "plan_id", "artifact_id"}
    # Permissions surfaced.
    assert s["permissions"]
