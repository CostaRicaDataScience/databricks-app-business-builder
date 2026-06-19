"""End-to-end: /run emits the cascarón scaffold and (with OBO) runs build-out."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from fastapi.testclient import TestClient

from composer.databricks.obo import HEADER_ACCESS_TOKEN, HEADER_EMAIL
from modules.app.main import app

client = TestClient(app)

SECRET_TOKEN = "dapi-cascaron-secret-token"


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


def test_run_offline_surfaces_scaffold_and_leaves_to_generate():
    res = client.post("/run", json=_payload())
    assert res.status_code == 200
    s = res.json()
    g = s["generated_app"]

    # New scaffold metadata is surfaced in the summary.
    assert g["manifest_path"] and g["manifest_path"].endswith("app.manifest.yaml")
    assert g["execution_plan_path"].endswith("EXECUTION_PLAN.md")
    assert g["contracts_path"].endswith("CONTRACTS.yaml")
    build_out = g["build_out"]
    # Offline: build-out did not run; files remain to_generate.
    assert build_out["phase"] == "not_started"
    assert build_out["files_generated"] == []
    assert build_out["files_to_generate"]

    # The manifest exists on disk and lists files as to_generate.
    manifest = yaml.safe_load(Path(g["manifest_path"]).read_text())
    assert all(f["status"] == "to_generate" for f in manifest["files"])


def _fake_ws_with_buildout() -> MagicMock:
    ws = MagicMock()
    ws.current_user.me.return_value = MagicMock(
        user_name="obo-user@example.com", display_name="OBO User"
    )
    # Codegen serving endpoint (Phase-A bootstrap preview).
    msg = MagicMock()
    msg.content = json.dumps(
        {"app.py": "import streamlit as st\nst.title('OBO Preview')\n"}
    )
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    ws.serving_endpoints.query.return_value = resp
    # Phase B planner (AI Gateway) returns OpenAI-compatible chat-completions.
    ws.api_client.do.return_value = {
        "choices": [{"message": {"content": "# built by opus\nprint('ok')\n"}}]
    }
    return ws


def test_run_with_obo_runs_buildout_and_flips_statuses():
    fake_ws = _fake_ws_with_buildout()
    with patch("composer.databricks.client.WorkspaceClient", return_value=fake_ws):
        res = client.post(
            "/run",
            json=_payload(),
            headers={
                HEADER_ACCESS_TOKEN: SECRET_TOKEN,
                HEADER_EMAIL: "obo-user@example.com",
            },
        )
    assert res.status_code == 200
    s = res.json()
    g = s["generated_app"]

    # Phase B ran via the planner endpoint and completed the build-out.
    assert g["build_out"]["phase"] == "complete"
    assert g["build_out"]["endpoint"] == "databricks-claude-opus-4"
    assert g["build_out"]["files_generated"]
    assert g["build_out"]["files_to_generate"] == []

    # On disk: statuses flipped to generated and content written.
    manifest = yaml.safe_load(Path(g["manifest_path"]).read_text())
    assert all(f["status"] == "generated" for f in manifest["files"])
    assert "built by opus" in (Path(g["output_path"]) / "app" / "app.py").read_text()

    # The planner call carried the AI Gateway request-tags header.
    _, kwargs = fake_ws.api_client.do.call_args
    assert "Databricks-Ai-Gateway-Request-Tags" in kwargs["headers"]

    # Token never leaks into the response.
    assert SECRET_TOKEN not in res.text
