from fastapi.testclient import TestClient

from modules.app.main import app


def test_intake_discovery_plan_generate_provision_flow():
    client = TestClient(app)

    intake_res = client.post(
        "/discovery-intake",
        json={
            "primary_use_case_description": "Build sales KPI assistant app",
            "user_stories": [
                "As analyst I want to review monthly sales",
                "As manager I want to query anomalies",
            ],
            "gold_tables": ["sales.gold_orders", "sales.gold_customers"],
            "existing_genies": ["sales_assistant", "new_sales_genie"],
            "workflow_requirements": "Daily refresh and weekly review",
            "style_preferences": "Clean dashboard with dark accents",
            "access_requirements": "Read UC + create genie + app create",
        },
    )
    assert intake_res.status_code == 200
    intake_id = intake_res.json()["intake_id"]

    discovery_res = client.post("/discovery-run", json={"intake_id": intake_id})
    assert discovery_res.status_code == 200
    report_id = discovery_res.json()["report_id"]

    confirm_res = client.post(
        "/discovery-confirm", json={"intake_id": intake_id, "report_id": report_id}
    )
    assert confirm_res.status_code == 200

    plan_res = client.post(
        "/build-plan", json={"intake_id": intake_id, "dry_run": True, "run_provisioning": True}
    )
    assert plan_res.status_code == 200
    plan_id = plan_res.json()["plan_id"]

    generate_res = client.post("/generate", json={"plan_id": plan_id})
    assert generate_res.status_code == 200
    assert "output_path" in generate_res.json()

    provision_res = client.post(
        "/provision",
        json={
            "intake_id": intake_id,
            "environment": "dev",
            "owner": "workspace-user",
            "use_case_slug": "sales-kpi-app",
            "resources": ["compute:serverless", "pipeline:sales_daily"],
        },
    )
    assert provision_res.status_code == 200
    operation_id = provision_res.json()["operation_id"]

    tag_res = client.get(f"/tagging-report/{operation_id}")
    assert tag_res.status_code == 200
    assert tag_res.json()["required_tags"]["project"] == "databricks-app-business-builder"
