from composer.blueprint.planner import build_blueprint
from composer.blueprint.validate import validate_blueprint
from composer.codegen.generator import generate_streamlit_app
from composer.core.artifacts import ArtifactStore
from composer.discovery.service import DiscoveryService
from composer.models.intake import IntakeSpec


def test_composer_discovery_and_codegen(tmp_path):
    intake = IntakeSpec(
        primary_use_case_description="Sales app",
        user_stories=["As analyst I want KPIs"],
        gold_tables=["sales.gold_orders", "sales.gold_customers"],
        existing_genies=["sales_assistant", "new_sales_genie"],
        workflow_requirements="daily refresh",
        style_preferences="clean",
        access_requirements="read+create",
    )
    store = ArtifactStore(str(tmp_path / ".appgen"))
    store.save_model("requirements.yaml", intake)

    report = DiscoveryService().run(intake)
    store.save_model("discovery_report.yaml", report)
    assert report.tables

    blueprint = build_blueprint(intake, report)
    validate_blueprint(blueprint)
    generated = generate_streamlit_app(blueprint, str(tmp_path / "generated"))
    assert generated["files_generated"]
