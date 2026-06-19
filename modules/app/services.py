"""Application services for intake, discovery, planning, and provisioning."""

from __future__ import annotations

import sys
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))

from composer.blueprint.planner import build_blueprint
from composer.blueprint.validate import validate_blueprint
from composer.codegen.generator import generate_streamlit_app
from composer.core.approvals import ApprovalGate
from composer.core.artifacts import ArtifactStore
from composer.discovery.service import DiscoveryService
from composer.llm.client import LLMClient
from composer.metadata.audit import build_metadata_quality_report
from composer.metadata.enrich import propose_metadata_updates
from composer.metadata.writer import apply_metadata_updates
from composer.models.blueprint import DiscoveryReport as ComposerDiscoveryReport
from composer.models.intake import IntakeSpec
from composer.permissions.preflight import run_preflight
from composer.provision.tagging import enforce_tags
from modules.core.config import AppSettings
from modules.core.logging import log
from modules.infra.databricks_auth import DatabricksConnectionService
from modules.domain.models import (
    AppIntent,
    BuildPlan,
    DiscoveryIntake,
    DiscoveryReport,
    DiscoveryStatus,
    GenieDiscovery,
    GeneratedArtifact,
    ProvisioningResult,
    TableDiscovery,
    TaggingReport,
)
from modules.infra.databricks_client import DatabricksApiClient
from modules.infra.tagging import TaggingPolicy
from modules.infra.repository import InMemoryRepository


class FoundationModelGateway:
    """Compatibility wrapper over composer LLM client."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._llm = LLMClient(
            # Reuse current settings structure with expected fields.
            type(
                "ComposerSettings",
                (),
                {
                    "foundation_model_endpoint": settings.foundation_model_provider,
                    "preferred_model": settings.preferred_model,
                },
            )()
        )

    def build_plan(self, intake: DiscoveryIntake) -> BuildPlan:
        composer_plan = self._llm.build_plan(_to_intake_spec(intake))
        return BuildPlan(
            plan_id=composer_plan.plan_id,
            summary=composer_plan.summary,
            implementation_steps=composer_plan.implementation_steps,
        )


class OrchestratorService:
    def __init__(
        self,
        settings: AppSettings,
        dbx_client: DatabricksApiClient,
        genai_gateway: FoundationModelGateway,
        tagging_policy: TaggingPolicy,
    ) -> None:
        self.settings = settings
        self.dbx_client = dbx_client
        self.genai_gateway = genai_gateway
        self.tagging_policy = tagging_policy
        self.connection = DatabricksConnectionService(settings)
        self.artifacts = ArtifactStore(root=".appgen")
        self.approvals = ApprovalGate(root=".appgen", dry_run=True)
        self.intake_repo: InMemoryRepository[DiscoveryIntake] = InMemoryRepository()
        self.discovery_repo: InMemoryRepository[DiscoveryReport] = InMemoryRepository()
        self.plan_repo: InMemoryRepository[BuildPlan] = InMemoryRepository()
        self.artifact_repo: InMemoryRepository[GeneratedArtifact] = InMemoryRepository()
        self.provision_repo: InMemoryRepository[ProvisioningResult] = InMemoryRepository()
        self.operation_repo: InMemoryRepository[dict] = InMemoryRepository()

    def submit_intake(self, intake: DiscoveryIntake) -> str:
        intake_id = str(uuid.uuid4())
        self.intake_repo.save(intake_id, intake)
        self.artifacts.save_dict("requirements.yaml", _to_intake_spec(intake).model_dump(mode="json"))
        log.info("discovery_intake_submitted", intake_id=intake_id)
        return intake_id

    def run_discovery(self, intake_id: str) -> DiscoveryReport:
        intake = self._require_intake(intake_id)
        composer_report = DiscoveryService().run(_to_intake_spec(intake))
        report = _from_composer_discovery(composer_report)
        self.discovery_repo.save(report.report_id, report)
        self.artifacts.save_dict("discovery_report.yaml", composer_report.model_dump(mode="json"))
        self.artifacts.save_dict("metadata_quality_report.yaml", build_metadata_quality_report(composer_report))
        return report

    def confirm_discovery_autofix(self, intake_id: str, report_id: str) -> dict:
        intake = self._require_intake(intake_id)
        report = self._require_discovery(report_id)
        self.approvals.ensure_allowed("discovery_autofix", approved=True)
        composer_report = _to_composer_discovery(report)
        proposals = propose_metadata_updates(composer_report)
        metadata_result = apply_metadata_updates(proposals, approved=True, dry_run=True)

        enriched_tables: list[str] = []
        created_genies: list[str] = []

        for table in report.tables:
            if table.status in {DiscoveryStatus.MISSING, DiscoveryStatus.NEEDS_ENRICHMENT}:
                self.dbx_client.enrich_table_metadata(
                    table_name=table.table_name,
                    table_description=f"Auto-generated description for {table.table_name}",
                    column_descriptions={
                        c: f"Auto-generated description for {c}"
                        for c in table.missing_columns or ["id", "value"]
                    },
                )
                enriched_tables.append(table.table_name)

        for genie in report.genies:
            if genie.status == DiscoveryStatus.NEEDS_CREATION:
                self.dbx_client.create_genie(
                    genie_name=genie.genie_name,
                    use_case_description=intake.primary_use_case_description,
                )
                created_genies.append(genie.genie_name)

        result = {
            "intake_id": intake_id,
            "report_id": report_id,
            "enriched_tables": enriched_tables,
            "created_genies": created_genies,
            "metadata_result": metadata_result,
        }
        op_id = str(uuid.uuid4())
        self.operation_repo.save(op_id, {"type": "discovery_confirm", "result": result})
        self.artifacts.save_dict("metadata_update_plan.yaml", {"proposals": proposals})
        self.artifacts.save_dict("metadata_apply_report.yaml", metadata_result)
        return result

    def build_plan(self, intake_id: str, dry_run: bool, run_provisioning: bool) -> BuildPlan:
        intake = self._require_intake(intake_id)
        intent = AppIntent(intake=intake, dry_run=dry_run, run_provisioning=run_provisioning)
        plan = self.genai_gateway.build_plan(intent.intake)
        self.plan_repo.save(plan.plan_id, plan)
        self.artifacts.save_dict("app_spec.yaml", asdict(plan))
        return plan

    def generate(self, plan_id: str) -> GeneratedArtifact:
        plan = self._require_plan(plan_id)
        intake = next(iter(self.intake_repo.list()), None)
        if intake is None:
            raise ValueError("No intake found to generate blueprint")
        discovery = next(iter(self.discovery_repo.list()), None)
        if discovery is None:
            raise ValueError("No discovery report found to generate blueprint")
        blueprint = build_blueprint(_to_intake_spec(intake), _to_composer_discovery(discovery))
        validate_blueprint(blueprint)
        self.artifacts.save_dict("final_build_plan.yaml", blueprint.model_dump(mode="json"))
        generated = generate_streamlit_app(blueprint, output_root=self.settings.output_root)
        artifact = GeneratedArtifact(
            artifact_id=str(uuid.uuid4()),
            output_path=generated["output_path"],
            files_generated=generated["files_generated"],
        )
        self.artifact_repo.save(artifact.artifact_id, artifact)
        self.artifacts.save_dict("generated_app_report.yaml", generated)
        return artifact

    def provision(
        self,
        intake_id: str,
        environment: str,
        owner: str,
        use_case_slug: str,
        resources: list[str],
    ) -> ProvisioningResult:
        intake = self._require_intake(intake_id)
        preflight = run_preflight(
            access_requirements=intake.access_requirements,
            capabilities={
                "read_catalog": True,
                "manage_genie": True,
                "create_databricks_app": True,
                "tag_resources": True,
            },
        )
        self.artifacts.save_dict("permission_report.yaml", preflight)
        if not preflight["ok"]:
            raise ValueError(f"Preflight failed: {preflight['missing_capabilities']}")
        trace_id = str(uuid.uuid4())
        tags = {
            "project": "databricks-app-business-builder",
            "environment": environment,
            "owner": owner,
            "use_case": use_case_slug,
            "trace_id": trace_id,
        }
        self.tagging_policy.validate(tags)

        planned = [
            "Validate permissions",
            "Apply metadata enrichment",
            "Create missing genies",
            "Tag compute/jobs/pipelines",
            "Create Databricks App resources",
        ]
        applied = [f"Tagged {resource}" for resource in resources]
        rollback_hints = [
            "Delete generated Genie if undesired",
            "Revert table descriptions manually if required",
        ]

        tagged = enforce_tags(environment, owner, use_case_slug, resources)
        tagging_report = TaggingReport(
            report_id=tagged.report_id,
            required_tags=tagged.required_tags,
            resources_tagged=tagged.resources_tagged,
        )
        result = ProvisioningResult(
            operation_id=str(uuid.uuid4()),
            actions_planned=planned,
            actions_applied=applied,
            rollback_hints=rollback_hints,
            tagging_report=tagging_report,
        )
        self.provision_repo.save(result.operation_id, result)
        self.artifacts.save_dict("tagging_report.yaml", asdict(tagging_report))
        self.operation_repo.save(
            result.operation_id,
            {
                "type": "provision",
                "intake_use_case": intake.primary_use_case_description,
                "result": asdict(result),
            },
        )
        return result

    def auth_status(self) -> dict:
        """Connection + permission status for the Databricks workspace."""
        return self.connection.status()

    def connect(self) -> dict:
        """Attempt to (re)resolve the workspace connection and report status.

        With the SDK this re-runs client resolution (host+token, profile, or
        service principal). It returns the same shape as ``auth_status`` so the
        UI can show connected/principal/host or exactly what is missing.
        """
        status = self.connection.status()
        log.info(
            "databricks_connect_attempt",
            connected=status["connected"],
            auth_mode=status["auth_mode"],
            sdk_available=status["sdk_available"],
        )
        return status

    def run_pipeline(self, intake: DiscoveryIntake) -> dict:
        """Run the full intake -> discovery -> autofix -> plan -> generate flow.

        Returns a human-friendly summary. Safe fixes (metadata enrichment) are
        applied automatically (dry-run); sensitive actions (creating Genies,
        provisioning) are surfaced as ``requires_approval`` rather than executed.
        Raw IDs are returned only under the secondary ``ids`` key for debugging.
        """
        steps: list[dict] = []

        # Step 1 - capture requirements.
        intake_id = self.submit_intake(intake)
        steps.append(
            {"key": "intake", "title": "Capturamos tus requerimientos", "status": "done"}
        )

        # Step 2 - connection + permission preview (the moment we connect).
        auth = self.auth_status()
        capabilities = {p["key"]: p["satisfied"] for p in auth["permissions"]}
        steps.append(
            {
                "key": "connect",
                "title": "Conexión a Databricks y permisos",
                "status": "done" if auth["connected"] else "needs_attention",
                "detail": auth["message"],
            }
        )

        # Step 3 - discovery of tables and genies.
        report = self.run_discovery(intake_id)
        tables_ok = [t.table_name for t in report.tables if t.status == DiscoveryStatus.EXISTS]
        tables_to_fix = [
            t.table_name
            for t in report.tables
            if t.status in {DiscoveryStatus.MISSING, DiscoveryStatus.NEEDS_ENRICHMENT}
        ]
        genies_existing = [
            g.genie_name for g in report.genies if g.status == DiscoveryStatus.EXISTS
        ]
        genies_to_create = [
            g.genie_name
            for g in report.genies
            if g.status == DiscoveryStatus.NEEDS_CREATION
        ]
        steps.append(
            {
                "key": "discovery",
                "title": "Revisamos tus datos y asistentes",
                "status": "done",
                "detail": f"{len(report.tables)} tablas y {len(report.genies)} asistentes revisados.",
            }
        )

        # Step 4 - safe autofix: metadata enrichment (dry-run, auto-approved).
        enriched_tables: list[str] = []
        self.approvals.ensure_allowed("metadata_autofix", approved=True)
        composer_report = _to_composer_discovery(report)
        proposals = propose_metadata_updates(composer_report)
        metadata_result = apply_metadata_updates(proposals, approved=True, dry_run=True)
        for table in report.tables:
            if table.status in {DiscoveryStatus.MISSING, DiscoveryStatus.NEEDS_ENRICHMENT}:
                self.dbx_client.enrich_table_metadata(
                    table_name=table.table_name,
                    table_description=f"Auto-generated description for {table.table_name}",
                    column_descriptions={
                        c: f"Auto-generated description for {c}"
                        for c in table.missing_columns or ["id", "value"]
                    },
                )
                enriched_tables.append(table.table_name)
        self.artifacts.save_dict("metadata_update_plan.yaml", {"proposals": proposals})
        self.artifacts.save_dict("metadata_apply_report.yaml", metadata_result)
        steps.append(
            {
                "key": "autofix",
                "title": "Mejoramos descripciones de datos faltantes",
                "status": "done",
                "detail": (
                    f"{len(enriched_tables)} tabla(s) mejorada(s) (simulado / dry-run)."
                    if enriched_tables
                    else "No se requirieron mejoras de metadata."
                ),
            }
        )

        # Step 5 - build plan + generate app scaffold.
        plan = self.build_plan(intake_id, dry_run=True, run_provisioning=False)
        artifact = self.generate(plan.plan_id)
        steps.append(
            {
                "key": "generate",
                "title": "Generamos el esqueleto de tu app",
                "status": "done",
                "detail": f"{len(artifact.files_generated)} archivo(s) en {artifact.output_path}.",
            }
        )

        # Permission preflight (surfaced, never silently bypassed).
        preflight = run_preflight(intake.access_requirements, capabilities)
        self.artifacts.save_dict("permission_report.yaml", preflight)

        # Sensitive actions are reported, not executed.
        requires_approval: list[str] = []
        for genie in genies_to_create:
            requires_approval.append(
                f"Crear el asistente Genie '{genie}' (requiere tu aprobación)."
            )
        requires_approval.append(
            "Publicar/provisionar la app en tu workspace (requiere tu aprobación)."
        )

        next_actions = [
            "Revisa los datos encontrados y las descripciones mejoradas.",
            "Aprueba la creación de asistentes y la publicación cuando estés listo.",
        ]
        if auth["missing"]:
            next_actions.insert(
                0,
                "Configura el acceso a Databricks: faltan "
                + ", ".join(auth["missing"])
                + ".",
            )

        summary = {
            "headline": "Listo: ejecutamos el flujo completo con tus requerimientos.",
            "steps": steps,
            "connection": {
                "connected": auth["connected"],
                "host": auth["host"],
                "principal": auth["principal"],
                "auth_mode": auth["auth_mode"],
                "message": auth["message"],
            },
            "data": {
                "tables_found": tables_ok,
                "tables_improved": tables_to_fix,
            },
            "assistants": {
                "existing": genies_existing,
                "to_create": genies_to_create,
            },
            "generated_app": {
                "output_path": artifact.output_path,
                "files": artifact.files_generated,
            },
            "permissions": auth["permissions"],
            "preflight_ok": preflight["ok"],
            "requires_approval": requires_approval,
            "next_actions": next_actions,
            "ids": {
                "intake_id": intake_id,
                "report_id": report.report_id,
                "plan_id": plan.plan_id,
                "artifact_id": artifact.artifact_id,
            },
        }
        self.operation_repo.save(
            intake_id, {"type": "run_pipeline", "summary": summary}
        )
        log.info("run_pipeline_completed", intake_id=intake_id, connected=auth["connected"])
        return summary

    def get_discovery_report(self, report_id: str) -> DiscoveryReport:
        return self._require_discovery(report_id)

    def get_tagging_report(self, operation_id: str) -> TaggingReport:
        provision = self.provision_repo.get(operation_id)
        if provision is None:
            raise ValueError(f"Unknown operation_id: {operation_id}")
        return provision.tagging_report

    def get_operation(self, operation_id: str) -> dict:
        operation = self.operation_repo.get(operation_id)
        if operation is None:
            raise ValueError(f"Unknown operation_id: {operation_id}")
        return operation

    def _require_intake(self, intake_id: str) -> DiscoveryIntake:
        intake = self.intake_repo.get(intake_id)
        if intake is None:
            raise ValueError(f"Unknown intake_id: {intake_id}")
        return intake

    def _require_discovery(self, report_id: str) -> DiscoveryReport:
        report = self.discovery_repo.get(report_id)
        if report is None:
            raise ValueError(f"Unknown report_id: {report_id}")
        return report

    def _require_plan(self, plan_id: str) -> BuildPlan:
        plan = self.plan_repo.get(plan_id)
        if plan is None:
            raise ValueError(f"Unknown plan_id: {plan_id}")
        return plan


def _to_intake_spec(intake: DiscoveryIntake) -> IntakeSpec:
    style_reference = None
    if intake.style_reference is not None:
        style_reference = {
            "source_type": intake.style_reference.source_type,
            "source_path_or_url": intake.style_reference.source_path_or_url,
            "style_guidelines_notes": intake.style_reference.style_guidelines_notes,
        }
    payload = {
        "primary_use_case_description": intake.primary_use_case_description,
        "user_stories": intake.user_stories,
        "gold_tables": intake.gold_tables,
        "existing_genies": intake.existing_genies,
        "workflow_requirements": intake.workflow_requirements,
        "style_preferences": intake.style_preferences,
        "access_requirements": intake.access_requirements,
        "style_reference": style_reference,
    }
    return IntakeSpec.model_validate(payload)


def _from_composer_discovery(report: ComposerDiscoveryReport) -> DiscoveryReport:
    tables = [
        TableDiscovery(
            table_name=t.name,
            status=DiscoveryStatus(t.status),
            has_table_description=t.status == "exists",
            missing_columns=["unknown_column"] if t.status == "needs_enrichment" else [],
        )
        for t in report.tables
    ]
    genies = [
        GenieDiscovery(
            genie_name=g.name,
            status=DiscoveryStatus(g.status),
            reason=g.details,
        )
        for g in report.genies
    ]
    return DiscoveryReport(report_id=report.report_id, tables=tables, genies=genies, summary=report.summary)


def _to_composer_discovery(report: DiscoveryReport) -> ComposerDiscoveryReport:
    from composer.models.blueprint import DiscoveryResourceStatus

    return ComposerDiscoveryReport(
        report_id=report.report_id,
        tables=[
            DiscoveryResourceStatus(name=t.table_name, status=t.status.value, details=None)
            for t in report.tables
        ],
        genies=[
            DiscoveryResourceStatus(name=g.genie_name, status=g.status.value, details=g.reason)
            for g in report.genies
        ],
        summary=report.summary,
    )
