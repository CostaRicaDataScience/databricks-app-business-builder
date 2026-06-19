"""Typer CLI for unified composer/appgen workflow."""

from __future__ import annotations

import typer

from composer.blueprint.planner import build_blueprint
from composer.blueprint.validate import validate_blueprint
from composer.codegen.generator import generate_streamlit_app
from composer.core.approvals import ApprovalGate
from composer.core.artifacts import ArtifactStore
from composer.core.config import load_settings
from composer.discovery.service import DiscoveryService
from composer.llm.client import LLMClient
from composer.metadata.audit import build_metadata_quality_report
from composer.metadata.enrich import propose_metadata_updates
from composer.metadata.writer import apply_metadata_updates
from composer.models.intake import IntakeSpec
from composer.permissions.preflight import run_preflight
from composer.provision.tagging import enforce_tags

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _artifact_store() -> ArtifactStore:
    settings = load_settings()
    return ArtifactStore(settings.appgen_dir)


@app.command("intake")
def intake(
    use_case: str,
    workflow: str,
    style: str,
    access: str,
    stories: list[str] = typer.Option(...),
    tables: list[str] = typer.Option(...),
    genies: list[str] = typer.Option([]),
) -> None:
    spec = IntakeSpec(
        primary_use_case_description=use_case,
        user_stories=stories,
        gold_tables=tables,
        existing_genies=genies,
        workflow_requirements=workflow,
        style_preferences=style,
        access_requirements=access,
    )
    store = _artifact_store()
    path = store.save_model("requirements.yaml", spec)
    typer.echo(f"saved intake at {path}")


@app.command("plan")
def plan() -> None:
    settings = load_settings()
    store = _artifact_store()
    intake = store.load_model("requirements.yaml", IntakeSpec)
    plan_model = LLMClient(settings).build_plan(intake)
    path = store.save_model("app_spec.yaml", plan_model)
    typer.echo(f"saved plan at {path}")


@app.command("discover")
def discover() -> None:
    store = _artifact_store()
    intake = store.load_model("requirements.yaml", IntakeSpec)
    report = DiscoveryService().run(intake)
    report_path = store.save_model("discovery_report.yaml", report)
    quality_path = store.save_dict("metadata_quality_report.yaml", build_metadata_quality_report(report))
    typer.echo(f"saved discovery at {report_path} and {quality_path}")


@app.command("propose-metadata")
def propose_metadata() -> None:
    from composer.models.blueprint import DiscoveryReport

    store = _artifact_store()
    report = store.load_model("discovery_report.yaml", DiscoveryReport)
    proposals = propose_metadata_updates(report)
    path = store.save_dict("metadata_update_plan.yaml", {"proposals": proposals})
    typer.echo(f"saved metadata proposals at {path}")


@app.command("apply-metadata")
def apply_metadata(approve: bool = typer.Option(False), dry_run: bool = typer.Option(True)) -> None:
    import yaml

    settings = load_settings()
    gate = ApprovalGate(root=settings.appgen_dir, dry_run=dry_run)
    gate.ensure_allowed(action="apply_metadata", approved=approve)
    with open(f"{settings.appgen_dir}/metadata_update_plan.yaml", "r", encoding="utf-8") as f:
        proposals = (yaml.safe_load(f) or {}).get("proposals", [])
    result = apply_metadata_updates(proposals, approved=approve, dry_run=dry_run)
    path = _artifact_store().save_dict("metadata_apply_report.yaml", result)
    typer.echo(f"saved metadata apply report at {path}")


@app.command("generate-app")
def generate_app() -> None:
    from composer.models.blueprint import DiscoveryReport

    settings = load_settings()
    store = _artifact_store()
    intake = store.load_model("requirements.yaml", IntakeSpec)
    discovery = store.load_model("discovery_report.yaml", DiscoveryReport)
    blueprint = build_blueprint(intake, discovery)
    validate_blueprint(blueprint)
    store.save_model("final_build_plan.yaml", blueprint)
    generated = generate_streamlit_app(blueprint, output_root=settings.output_root)
    store.save_dict("generated_app_report.yaml", generated)
    typer.echo(f"generated app at {generated['output_path']}")


@app.command("preflight")
def preflight() -> None:
    store = _artifact_store()
    intake = store.load_model("requirements.yaml", IntakeSpec)
    result = run_preflight(
        access_requirements=intake.access_requirements,
        capabilities={
            "read_catalog": True,
            "manage_genie": True,
            "create_databricks_app": True,
            "tag_resources": True,
        },
    )
    path = store.save_dict("permission_report.yaml", result)
    typer.echo(f"saved preflight report at {path}")


@app.command("tag-report")
def tag_report(
    environment: str = "dev",
    owner: str = "workspace-user",
    use_case_slug: str = "default-use-case",
) -> None:
    report = enforce_tags(environment, owner, use_case_slug, ["compute:serverless"])
    path = _artifact_store().save_model("tagging_report.yaml", report)
    typer.echo(f"saved tagging report at {path}")


if __name__ == "__main__":
    app()
