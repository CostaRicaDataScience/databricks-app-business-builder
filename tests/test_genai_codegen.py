"""Tests for GenAI codegen via a Databricks serving endpoint.

Verifies: when a workspace client is available the LLM path is invoked and its
output is written into the generated app; when unavailable, the deterministic
template fallback is used.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from composer.blueprint.planner import build_blueprint
from composer.codegen.generator import generate_streamlit_app
from composer.llm.client import LLMClient
from composer.models.blueprint import DiscoveryReport, DiscoveryResourceStatus
from composer.models.intake import IntakeSpec


class _Settings:
    foundation_model_endpoint = "databricks-claude-sonnet"
    preferred_model = "claude"


def _intake() -> IntakeSpec:
    return IntakeSpec(
        primary_use_case_description="Sales KPI app",
        user_stories=["As analyst I want KPIs"],
        gold_tables=["sales.gold_orders"],
        existing_genies=[],
        workflow_requirements="daily",
        style_preferences="dark",
        access_requirements="read",
    )


def _discovery() -> DiscoveryReport:
    return DiscoveryReport(
        report_id="r1",
        tables=[DiscoveryResourceStatus(name="sales.gold_orders", status="exists")],
        genies=[],
        summary="ok",
    )


def _serving_response(content: str) -> MagicMock:
    """Mimic the OpenAI-compatible serving-endpoint query response shape."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_generate_app_source_returns_none_without_workspace_client():
    llm = LLMClient(_Settings(), workspace_client=None)
    blueprint = build_blueprint(_intake(), _discovery())
    assert llm.generate_app_source(_intake(), blueprint, _discovery()) is None


def test_generate_app_source_invokes_serving_endpoint():
    fake_ws = MagicMock()
    generated_app_py = "import streamlit as st\nst.title('LLM Generated Sales App')\n"
    fake_ws.serving_endpoints.query.return_value = _serving_response(
        '{"app.py": "' + generated_app_py.replace("\n", "\\n") + '", '
        '"requirements.txt": "streamlit\\n"}'
    )
    llm = LLMClient(_Settings(), workspace_client=fake_ws)
    blueprint = build_blueprint(_intake(), _discovery())

    files = llm.generate_app_source(_intake(), blueprint, _discovery())

    # The serving endpoint was queried with the configured endpoint name.
    fake_ws.serving_endpoints.query.assert_called_once()
    _, kwargs = fake_ws.serving_endpoints.query.call_args
    assert kwargs["name"] == "databricks-claude-sonnet"
    assert files is not None
    assert "LLM Generated Sales App" in files["app.py"]
    assert "requirements.txt" in files


def test_generated_output_written_to_disk(tmp_path: Path):
    fake_ws = MagicMock()
    fake_ws.serving_endpoints.query.return_value = _serving_response(
        '{"app.py": "import streamlit as st\\nst.title(\'Model App\')\\n"}'
    )
    llm = LLMClient(_Settings(), workspace_client=fake_ws)
    blueprint = build_blueprint(_intake(), _discovery())
    files = llm.generate_app_source(_intake(), blueprint, _discovery())

    result = generate_streamlit_app(blueprint, str(tmp_path / "out"), files=files)
    assert result["source"] == "llm"
    app_py = Path(result["output_path"]) / "app.py"
    assert "Model App" in app_py.read_text()


def test_generator_falls_back_to_template(tmp_path: Path):
    blueprint = build_blueprint(_intake(), _discovery())
    result = generate_streamlit_app(blueprint, str(tmp_path / "out"), files=None)
    assert result["source"] == "template"
    app_py = Path(result["output_path"]) / "app.py"
    assert "Generated App" in app_py.read_text()


def test_malformed_model_output_degrades_to_none():
    fake_ws = MagicMock()
    fake_ws.serving_endpoints.query.return_value = _serving_response(
        "sorry, I cannot help with that"
    )
    llm = LLMClient(_Settings(), workspace_client=fake_ws)
    blueprint = build_blueprint(_intake(), _discovery())
    assert llm.generate_app_source(_intake(), blueprint, _discovery()) is None


def test_codegen_fenced_json_is_parsed():
    fake_ws = MagicMock()
    fake_ws.serving_endpoints.query.return_value = _serving_response(
        '```json\n{"app.py": "print(1)\\n"}\n```'
    )
    llm = LLMClient(_Settings(), workspace_client=fake_ws)
    blueprint = build_blueprint(_intake(), _discovery())
    files = llm.generate_app_source(_intake(), blueprint, _discovery())
    assert files == {"app.py": "print(1)\n"}
