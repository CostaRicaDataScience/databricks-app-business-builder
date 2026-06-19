"""Application services for intake, discovery, planning, and provisioning."""

from __future__ import annotations

import sys
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "src"))

from composer.blueprint.planner import build_blueprint
from composer.blueprint.validate import validate_blueprint
from composer.codegen.cascaron import emit_cascaron
from composer.codegen.generator import generate_streamlit_app
from composer.core.approvals import ApprovalGate
from composer.core.artifacts import ArtifactStore
from composer.databricks.inventory import collect_inventory
from composer.databricks.obo import RequestAuth
from composer.discovery.service import DiscoveryService
from composer.llm.client import LLMClient
from composer.mcp.client import MCPClient
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

    def _mcp_client(self, auth: RequestAuth | None = None) -> MCPClient:
        settings = self.connection.composer_settings
        token = (
            auth.user_token
            if (auth is not None and auth.is_obo)
            else settings.databricks_token
        )
        return MCPClient.from_settings(settings, token=token)

    def _llm_client(self, auth: RequestAuth | None = None) -> LLMClient:
        workspace_client = self.connection.workspace_client(auth)
        return LLMClient(
            self.connection.composer_settings, workspace_client=workspace_client
        )

    def run_discovery(self, intake_id: str, auth: RequestAuth | None = None) -> DiscoveryReport:
        intake = self._require_intake(intake_id)
        # Only use the live workspace for real verification when we are actually
        # connected (authenticated). Otherwise stay honest and report unknown.
        connected = self.connection.status(auth)["connected"]
        workspace = self.connection.databricks_client(auth) if connected else None
        composer_report = DiscoveryService(
            mcp_client=self._mcp_client(auth),
            workspace=workspace,
        ).run(_to_intake_spec(intake))
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

    def generate(
        self,
        plan_id: str,
        auth: RequestAuth | None = None,
        inventory: dict | None = None,
        connected: bool | None = None,
    ) -> GeneratedArtifact:
        plan = self._require_plan(plan_id)
        intake = next(iter(self.intake_repo.list()), None)
        if intake is None:
            raise ValueError("No intake found to generate blueprint")
        discovery = next(iter(self.discovery_repo.list()), None)
        if discovery is None:
            raise ValueError("No discovery report found to generate blueprint")
        intake_spec = _to_intake_spec(intake)
        composer_discovery = _to_composer_discovery(discovery)
        blueprint = build_blueprint(intake_spec, composer_discovery)
        validate_blueprint(blueprint)
        self.artifacts.save_dict("final_build_plan.yaml", blueprint.model_dump(mode="json"))
        # Generate the bootstrap entrypoint preview with the codegen serving
        # endpoint (as the OBO user when a forwarded token is present); fall back
        # to the template offline. The resource inventory (GET results + POST
        # plan) is fed to the model so the preview wires real resources.
        llm = self._llm_client(auth)
        generated_files = llm.generate_app_source(
            intake_spec, blueprint, composer_discovery, inventory=inventory
        )
        generated = generate_streamlit_app(
            blueprint,
            output_root=self.settings.output_root,
            files=generated_files,
        )
        output_path = generated["output_path"]
        # -- Phase A: deterministic cascarón (always; offline-safe) ---------
        # Emits app.manifest.yaml (source of truth), EXECUTION_PLAN.md,
        # CONTRACTS.yaml, spec/* and app/ stub files with TODO(build-out)
        # markers. This is what the Phase B build-out LLM follows.
        cascaron = emit_cascaron(
            app_dir=output_path,
            blueprint=blueprint,
            intake=intake_spec,
            discovery=composer_discovery,
            inventory=inventory,
            codegen_endpoint=llm.endpoint,
            planner_endpoint=llm.planner_endpoint,
        )
        # Always drop a RESOURCES.md so the skeleton documents the workspace
        # GET inventory and the POST plan, even in the offline template path.
        extra_files = set(cascaron.get("scaffold_files") or [])
        if inventory is not None:
            self._write_resources_doc(output_path, inventory)
            extra_files.add(str(Path(output_path) / "RESOURCES.md"))

        # -- Phase B: Claude Opus build-out via the AI Gateway --------------
        # Runs only when connected and a planner endpoint is available; otherwise
        # the scaffold stays valid with all files `to_generate`.
        if connected is None:
            connected = self.connection.status(auth)["connected"]
        build_out = {
            "endpoint": llm.planner_endpoint,
            "generated": [],
            "remaining": list(cascaron.get("files_to_generate") or []),
            "phase": "not_started",
            "skipped": True,
            "reason": "not_connected",
        }
        if connected and llm.planner_endpoint:
            build_out = llm.build_out_cascaron(output_path)
        files_built_out = list(build_out.get("generated") or [])

        generated["files_generated"] = sorted(
            set(generated["files_generated"]) | extra_files
        )
        source = generated.get("source", "template")
        preview = _read_preview(generated.get("files_generated") or [])
        artifact = GeneratedArtifact(
            artifact_id=str(uuid.uuid4()),
            output_path=output_path,
            files_generated=generated["files_generated"],
            source=source,
            generator_endpoint=llm.endpoint if source == "llm" else None,
            preview=preview,
            manifest_path=cascaron.get("manifest_path"),
            execution_plan_path=cascaron.get("execution_plan_path"),
            contracts_path=cascaron.get("contracts_path"),
            files_to_generate=list(build_out.get("remaining") or []),
            files_built_out=files_built_out,
            build_out_phase=build_out.get("phase", "not_started"),
            build_out_endpoint=build_out.get("endpoint"),
        )
        self.artifact_repo.save(artifact.artifact_id, artifact)
        self.artifacts.save_dict("generated_app_report.yaml", generated)
        self.artifacts.save_dict(
            "cascaron_buildout_report.yaml",
            {
                "manifest_path": cascaron.get("manifest_path"),
                "execution_plan_path": cascaron.get("execution_plan_path"),
                "contracts_path": cascaron.get("contracts_path"),
                "build_out": build_out,
            },
        )
        return artifact

    @staticmethod
    def _write_resources_doc(output_path: str, inventory: dict) -> None:
        """Write RESOURCES.md summarizing GET inventory and the POST plan."""
        lines = ["# Workspace resources", ""]
        lines.append("## Existing (GET)")
        for key, info in (inventory.get("resources") or {}).items():
            mark = "checked" if info.get("checked") else "not verified"
            existing = ", ".join(info.get("existing") or []) or "—"
            lines.append(f"- **{key}** ({mark}): {existing}")
        lines.append("")
        lines.append("## To create (POST)")
        for item in inventory.get("to_create") or []:
            lines.append(
                f"- **{item.get('resource_type')}** `{item.get('name')}`"
                f" — {item.get('reason')}"
            )
        blockers = inventory.get("blockers") or []
        if blockers:
            lines.append("")
            lines.append("## Blockers")
            for b in blockers:
                lines.append(f"- {b}")
        try:
            (Path(output_path) / "RESOURCES.md").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
        except Exception:  # pragma: no cover - best effort
            pass

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

    def auth_status(self, auth: RequestAuth | None = None) -> dict:
        """Connection + permission status for the Databricks workspace.

        When a forwarded OBO user token is present, status reflects the
        signed-in user and reports ``auth_mode='databricks_app_obo'``.
        """
        return self.connection.status(auth)

    def connect(self, auth: RequestAuth | None = None) -> dict:
        """Attempt to (re)resolve the workspace connection and report status.

        With the SDK this re-runs client resolution (host+token, profile, or
        service principal). It returns the same shape as ``auth_status`` so the
        UI can show connected/principal/host or exactly what is missing.
        """
        status = self.connection.status(auth)
        log.info(
            "databricks_connect_attempt",
            connected=status["connected"],
            auth_mode=status["auth_mode"],
            sdk_available=status["sdk_available"],
        )
        return status

    def run_pipeline(self, intake: DiscoveryIntake, auth: RequestAuth | None = None) -> dict:
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
        auth_info = self.auth_status(auth)
        capabilities = {p["key"]: p["satisfied"] for p in auth_info["permissions"]}
        steps.append(
            {
                "key": "connect",
                "title": "Conexión a Databricks y permisos",
                "status": "done" if auth_info["connected"] else "needs_attention",
                "detail": auth_info["message"],
            }
        )

        # Step 3 - discovery of tables and genies.
        report = self.run_discovery(intake_id, auth)
        tables_ok = [t.table_name for t in report.tables if t.status == DiscoveryStatus.EXISTS]
        tables_to_fix = [
            t.table_name
            for t in report.tables
            if t.status in {DiscoveryStatus.MISSING, DiscoveryStatus.NEEDS_ENRICHMENT}
        ]
        tables_unverified = [
            t.table_name for t in report.tables if t.status == DiscoveryStatus.UNKNOWN
        ]
        genies_existing = [
            g.genie_name for g in report.genies if g.status == DiscoveryStatus.EXISTS
        ]
        genies_to_create = [
            g.genie_name
            for g in report.genies
            if g.status == DiscoveryStatus.NEEDS_CREATION
        ]
        genies_unverified = [
            g.genie_name for g in report.genies if g.status == DiscoveryStatus.UNKNOWN
        ]
        discovery_detail = (
            f"{len(report.tables)} tabla(s) y {len(report.genies)} asistente(s) revisados."
        )
        if tables_unverified:
            discovery_detail += (
                f" {len(tables_unverified)} sin verificar (requiere conexión)."
            )
        steps.append(
            {
                "key": "discovery",
                "title": "Revisamos tus datos y asistentes",
                "status": "needs_attention" if tables_unverified else "done",
                "detail": discovery_detail,
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

        # Step 5 - inventory: GET existing workspace resources, map POSTs to make.
        inventory = collect_inventory(
            client=self.connection.databricks_client(auth),
            intake=_to_intake_spec(intake),
            discovery=_to_composer_discovery(report),
            serving_endpoint=self.connection.composer_settings.foundation_model_endpoint,
            connected=auth_info["connected"],
        )
        self.artifacts.save_dict("resource_inventory.yaml", inventory["resources"])
        self.artifacts.save_dict(
            "resource_creation_plan.yaml",
            {"to_create": inventory["to_create"], "blockers": inventory["blockers"]},
        )
        steps.append(
            {
                "key": "resources",
                "title": "Revisamos los recursos de tu workspace",
                "status": "done" if inventory["checked"] else "needs_attention",
                "detail": (
                    f"{len(inventory['to_create'])} recurso(s) por crear."
                    if inventory["checked"]
                    else "Inventario pendiente: conéctate para verificar recursos existentes."
                ),
            }
        )

        # Step 6 - build plan + generate cascarón scaffold (with the inventory).
        plan = self.build_plan(intake_id, dry_run=True, run_provisioning=False)
        artifact = self.generate(
            plan.plan_id, auth, inventory=inventory, connected=auth_info["connected"]
        )
        n_built = len(artifact.files_built_out)
        n_pending = len(artifact.files_to_generate)
        if n_built:
            gen_detail = (
                f"Esqueleto (cascarón) creado y {n_built} archivo(s) completados "
                f"por Claude Opus ({artifact.build_out_endpoint}); "
                f"{n_pending} pendiente(s) en {artifact.output_path}."
            )
        else:
            gen_detail = (
                f"Esqueleto (cascarón) creado con {n_pending} archivo(s) por "
                f"construir (build-out de Opus pendiente de conexión) en "
                f"{artifact.output_path}."
            )
        steps.append(
            {
                "key": "generate",
                "title": "Generamos el esqueleto (cascarón) de tu app",
                "status": "done",
                "detail": gen_detail,
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
        if auth_info["missing"]:
            next_actions.insert(
                0,
                "Configura el acceso a Databricks: faltan "
                + ", ".join(auth_info["missing"])
                + ".",
            )

        summary = {
            "headline": "Listo: ejecutamos el flujo completo con tus requerimientos.",
            "steps": steps,
            "connection": {
                "connected": auth_info["connected"],
                "host": auth_info["host"],
                "principal": auth_info["principal"],
                "auth_mode": auth_info["auth_mode"],
                "message": auth_info["message"],
            },
            "data": {
                "tables_found": tables_ok,
                "tables_improved": tables_to_fix,
                "tables_unverified": tables_unverified,
            },
            "assistants": {
                "existing": genies_existing,
                "to_create": genies_to_create,
                "unverified": genies_unverified,
            },
            "generated_app": {
                "output_path": artifact.output_path,
                "files": artifact.files_generated,
                "source": artifact.source,
                "generated_by": (
                    f"modelo · {artifact.generator_endpoint}"
                    if artifact.source == "llm"
                    else "plantilla base (sin conexión a un modelo)"
                ),
                "endpoint": artifact.generator_endpoint,
                "preview": artifact.preview,
                # Two-phase cascarón scaffold metadata.
                "manifest_path": artifact.manifest_path,
                "execution_plan_path": artifact.execution_plan_path,
                "contracts_path": artifact.contracts_path,
                "build_out": {
                    "phase": artifact.build_out_phase,
                    "endpoint": artifact.build_out_endpoint,
                    "files_generated": artifact.files_built_out,
                    "files_to_generate": artifact.files_to_generate,
                },
            },
            "resources": inventory["resources"],
            "to_create": inventory["to_create"],
            "blockers": inventory["blockers"],
            "permissions": auth_info["permissions"],
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
        log.info("run_pipeline_completed", intake_id=intake_id, connected=auth_info["connected"])
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


def _read_preview(files_generated: list[str], limit: int = 600) -> str | None:
    """Return a short preview of the generated app's entrypoint (app.py).

    Best-effort and never raises; used only to show the user a glimpse of the
    generated skeleton in the result panel.
    """
    app_py = next((p for p in files_generated if p.endswith("app.py")), None)
    target = app_py or (files_generated[0] if files_generated else None)
    if not target:
        return None
    try:
        text = Path(target).read_text(encoding="utf-8")
    except Exception:
        return None
    return text[:limit] + ("…" if len(text) > limit else "")


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
