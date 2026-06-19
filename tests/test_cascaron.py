"""Tests for the two-phase cascarón scaffold.

Phase A — deterministic emission (offline): manifest with files[].status, the
EXECUTION_PLAN, CONTRACTS, spec/ files, app/ stubs with TODO markers, app.yaml.
Phase B — Claude Opus build-out via the AI Gateway: flips statuses to
``generated`` and writes file contents, attaches request-tags header, and
degrades gracefully when offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from composer.blueprint.planner import build_blueprint
from composer.codegen.cascaron import emit_cascaron
from composer.llm.client import LLMClient
from composer.models.blueprint import DiscoveryReport, DiscoveryResourceStatus
from composer.models.intake import IntakeSpec


class _Settings:
    foundation_model_endpoint = "databricks-claude-sonnet"
    planner_model_endpoint = "databricks-claude-opus-4"
    preferred_model = "claude"


def _intake() -> IntakeSpec:
    return IntakeSpec(
        primary_use_case_description="Sales KPI app",
        user_stories=["As analyst I want KPIs"],
        gold_tables=["sales.gold_orders"],
        existing_genies=["sales_assistant"],
        workflow_requirements="daily",
        style_preferences="dark",
        access_requirements="read",
    )


def _discovery() -> DiscoveryReport:
    return DiscoveryReport(
        report_id="r1",
        tables=[DiscoveryResourceStatus(name="sales.gold_orders", status="exists")],
        genies=[DiscoveryResourceStatus(name="sales_assistant", status="exists")],
        summary="ok",
    )


def _inventory() -> dict:
    return {
        "checked": True,
        "resources": {
            "serving_endpoints": {"checked": True, "existing": ["e1"], "note": "ok"},
        },
        "to_create": [
            {
                "resource_type": "databricks_app",
                "name": "business-builder-generated-app",
                "method": "POST",
                "reason": "publish",
                "verified": True,
            }
        ],
        "blockers": ["table x missing"],
    }


def _emit(tmp_path: Path) -> dict:
    blueprint = build_blueprint(_intake(), _discovery())
    return emit_cascaron(
        app_dir=str(tmp_path / "app"),
        blueprint=blueprint,
        intake=_intake(),
        discovery=_discovery(),
        inventory=_inventory(),
        codegen_endpoint="databricks-claude-sonnet",
        planner_endpoint="databricks-claude-opus-4",
    )


# -- Phase A ---------------------------------------------------------------


def test_cascaron_emits_manifest_as_source_of_truth(tmp_path: Path):
    res = _emit(tmp_path)
    manifest = yaml.safe_load(Path(res["manifest_path"]).read_text())

    assert manifest["kind"] == "databricks-app-cascaron"
    # files[] each declare path / status / depends_on / produced_by_task.
    files = manifest["files"]
    assert files, "manifest must enumerate target files"
    for entry in files:
        assert set(entry) >= {"path", "purpose", "status", "depends_on", "produced_by_task"}
        assert entry["status"] == "to_generate"
    # Source-of-truth content: intake, discovery, inventory + POST plan, refs.
    assert manifest["intake"]["gold_tables"] == ["sales.gold_orders"]
    assert manifest["discovery"]["summary"] == "ok"
    assert manifest["resources"]["to_create"]
    assert manifest["resources"]["blockers"] == ["table x missing"]
    assert manifest["references"]["serving_endpoints"]["planner"] == "databricks-claude-opus-4"
    # OBO + scopes documented for the generated app.
    dbx = manifest["runtime"]["databricks_apps"]
    assert dbx["authorization"] == "user_authorization_obo"
    assert dbx["obo_header"] == "x-forwarded-access-token"
    assert "sql" in dbx["required_oauth_scopes"]
    assert "dashboards.genie" in dbx["required_oauth_scopes"]


def test_cascaron_emits_plan_contracts_and_spec(tmp_path: Path):
    res = _emit(tmp_path)
    base = Path(res["output_path"])

    plan = (base / "EXECUTION_PLAN.md").read_text()
    assert "Execution Plan" in plan
    assert "Build-out tasks" in plan
    # Each task is enumerated for the build-out LLM.
    assert "`app/app.py`" in plan

    contracts = yaml.safe_load((base / "CONTRACTS.yaml").read_text())
    names = {c["name"] for c in contracts["contracts"]}
    assert {"AppConfig", "UserAuth", "DataAccess", "Page"} <= names
    # Genie contract present because the intake references a genie.
    assert "GenieClient" in names

    # spec/ holds the structured inputs as files.
    for spec_file in (
        "requirements.yaml",
        "discovery_report.yaml",
        "resource_inventory.yaml",
        "resource_creation_plan.yaml",
    ):
        assert (base / "spec" / spec_file).exists()
    creation = yaml.safe_load((base / "spec" / "resource_creation_plan.yaml").read_text())
    assert "to_create" in creation and "blockers" in creation


def test_cascaron_emits_stub_files_with_todo_markers(tmp_path: Path):
    res = _emit(tmp_path)
    base = Path(res["output_path"])

    app_py = (base / "app" / "app.py").read_text()
    assert "TODO(build-out):" in app_py
    # Cross-reference back to the manifest entry.
    assert "app.manifest.yaml" in app_py
    # OBO header reference per the auth doc.
    assert "x-forwarded-access-token" in app_py

    data_access = (base / "app" / "data_access.py").read_text()
    assert "TODO(build-out):" in data_access

    # requirements.txt is real content, not a stub docstring.
    reqs = (base / "requirements.txt").read_text()
    assert "streamlit" in reqs
    assert "databricks-sdk" in reqs


def test_cascaron_app_yaml_command_targets_entrypoint(tmp_path: Path):
    res = _emit(tmp_path)
    app_yaml = yaml.safe_load((Path(res["output_path"]) / "app.yaml").read_text())
    assert app_yaml["command"] == ["streamlit", "run", "app/app.py"]


# -- Phase B ---------------------------------------------------------------


def _chat_response(content: str) -> dict:
    """OpenAI-compatible chat-completions dict, as the AI Gateway returns."""
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_buildout_flips_statuses_and_writes_files(tmp_path: Path):
    res = _emit(tmp_path)
    base = Path(res["output_path"])

    fake_ws = MagicMock()
    fake_ws.api_client.do.return_value = _chat_response("# generated content\nprint('ok')\n")

    llm = LLMClient(_Settings(), workspace_client=fake_ws)
    out = llm.build_out_cascaron(str(base))

    # All to_generate files were filled and statuses flipped.
    assert out["skipped"] is False
    assert out["phase"] == "complete"
    assert out["remaining"] == []
    assert out["generated"], "should report generated files"

    manifest = yaml.safe_load((base / "app.manifest.yaml").read_text())
    assert all(f["status"] == "generated" for f in manifest["files"])
    assert manifest["build_out"]["phase"] == "complete"
    # Content was written from the planner output.
    assert "generated content" in (base / "app" / "app.py").read_text()


def test_buildout_attaches_request_tags_header(tmp_path: Path):
    res = _emit(tmp_path)
    base = Path(res["output_path"])

    fake_ws = MagicMock()
    fake_ws.api_client.do.return_value = _chat_response("print(1)\n")

    llm = LLMClient(_Settings(), workspace_client=fake_ws)
    llm.build_out_cascaron(str(base))

    assert fake_ws.api_client.do.called
    _, kwargs = fake_ws.api_client.do.call_args
    headers = kwargs["headers"]
    assert "Databricks-Ai-Gateway-Request-Tags" in headers
    tags = json.loads(headers["Databricks-Ai-Gateway-Request-Tags"])
    assert tags["project"] == "databricks-app-business-builder"
    assert tags["phase"] == "build-out"
    # The planner endpoint (Opus) is the invocation target, not the codegen one.
    args, _ = fake_ws.api_client.do.call_args
    assert "databricks-claude-opus-4" in args[1]


def test_buildout_degrades_when_offline(tmp_path: Path):
    res = _emit(tmp_path)
    base = Path(res["output_path"])

    llm = LLMClient(_Settings(), workspace_client=None)
    out = llm.build_out_cascaron(str(base))

    assert out["skipped"] is True
    assert out["reason"] == "no_workspace_client"
    # Files remain to_generate; the scaffold is still valid.
    manifest = yaml.safe_load((base / "app.manifest.yaml").read_text())
    assert all(f["status"] == "to_generate" for f in manifest["files"])
    assert out["remaining"]


def test_buildout_non_dict_response_leaves_to_generate(tmp_path: Path):
    """A mock workspace client without a configured dict return must not write."""
    res = _emit(tmp_path)
    base = Path(res["output_path"])

    fake_ws = MagicMock()  # api_client.do returns a MagicMock, not a dict
    llm = LLMClient(_Settings(), workspace_client=fake_ws)
    out = llm.build_out_cascaron(str(base))

    assert out["generated"] == []
    assert out["remaining"]
    manifest = yaml.safe_load((base / "app.manifest.yaml").read_text())
    assert all(f["status"] == "to_generate" for f in manifest["files"])


# -- Config ----------------------------------------------------------------


def test_planner_endpoint_config_exposed(monkeypatch):
    import composer.core.config as composer_config
    import modules.core.config as app_config

    monkeypatch.setenv("PLANNER_MODEL_ENDPOINT", "my-opus-endpoint")
    assert composer_config.load_settings().planner_model_endpoint == "my-opus-endpoint"
    assert app_config.load_settings().planner_model_endpoint == "my-opus-endpoint"


def test_planner_endpoint_default():
    import composer.core.config as composer_config

    settings = composer_config.Settings(
        databricks_host="h",
        databricks_token=None,
        databricks_profile=None,
        auth_mode="user_workspace",
        sp_client_id=None,
        sp_client_secret=None,
        foundation_model_endpoint="databricks-claude-sonnet",
        preferred_model="claude",
        fallback_model="fb",
        appgen_dir=".appgen",
        output_root="./generated_apps",
        dry_run_default=True,
    )
    llm = LLMClient(settings, workspace_client=None)
    assert llm.planner_endpoint == "databricks-claude-opus-4"
    assert llm.endpoint == "databricks-claude-sonnet"
