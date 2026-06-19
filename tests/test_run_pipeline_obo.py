"""End-to-end: /run threads the OBO user token into discovery + GenAI codegen."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from composer.databricks.obo import HEADER_ACCESS_TOKEN, HEADER_EMAIL, MODE_OBO
from modules.app.main import app

client = TestClient(app)

SECRET_TOKEN = "dapi-run-pipeline-secret-token"


def _payload() -> dict:
    return {
        "primary_use_case_description": "Comparar ventas por región",
        "user_stories": ["Como analista quiero ver KPIs"],
        "gold_tables": ["sales.gold_orders"],
        "existing_genies": ["sales_assistant"],
        "workflow_requirements": "Se actualiza cada día.",
        "style_preferences": "Tema oscuro.",
        "access_requirements": "Equipo de ventas.",
    }


def _fake_workspace_client() -> MagicMock:
    ws = MagicMock()
    ws.current_user.me.return_value = MagicMock(
        user_name="obo-user@example.com", display_name="OBO User"
    )
    message = MagicMock()
    message.content = json.dumps(
        {"app.py": "import streamlit as st\nst.title('OBO Generated App')\n"}
    )
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    ws.serving_endpoints.query.return_value = resp
    return ws


def test_run_with_obo_uses_user_token_and_model_codegen():
    fake_ws = _fake_workspace_client()
    with patch(
        "composer.databricks.client.WorkspaceClient", return_value=fake_ws
    ):
        res = client.post(
            "/run",
            json=_payload(),
            headers={
                HEADER_ACCESS_TOKEN: SECRET_TOKEN,
                HEADER_EMAIL: "obo-user@example.com",
            },
        )
    assert res.status_code == 200
    summary = res.json()

    # OBO mode surfaced in the connection block; user identity resolved.
    assert summary["connection"]["auth_mode"] == MODE_OBO
    assert summary["connection"]["principal"] == "obo-user@example.com"

    # The serving endpoint was queried (model-driven codegen ran as the user).
    assert fake_ws.serving_endpoints.query.called

    # The generated app contains the model output, not the deterministic stub.
    app_py = Path(summary["generated_app"]["output_path"]) / "app.py"
    assert "OBO Generated App" in app_py.read_text()

    # Token never leaks into the response.
    assert SECRET_TOKEN not in res.text
