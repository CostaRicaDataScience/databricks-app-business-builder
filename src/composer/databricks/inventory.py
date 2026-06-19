"""Workspace resource inventory: GET existing resources, map what to POST.

Before generating the app skeleton we take stock of the user's workspace by
reading the resources the app may depend on, then map exactly what is missing
and must be created. This makes the generated output reflect *real* workspace
state, not just the client's free-text input.

Resource families covered (Databricks REST API references):

* serving endpoints  — https://docs.databricks.com/api/workspace/servingendpoints
* genie spaces       — https://docs.databricks.com/api/workspace/genie
* tables (UC)        — https://docs.databricks.com/api/workspace/tables
* volumes (UC)       — https://docs.databricks.com/api/workspace/volumes
* knowledge assistants — https://docs.databricks.com/api/workspace/knowledgeassistants
* environments       — https://docs.databricks.com/api/workspace/environments

Every read is best-effort: when we are not connected (or the SDK/endpoint is
unavailable) the resource is reported as ``checked=False`` ("not verified")
instead of being faked, and the POST plan is marked as pending verification.
"""

from __future__ import annotations

from composer.models.blueprint import DiscoveryReport
from composer.models.intake import IntakeSpec


def _catalog_schema_pairs(tables: list[str]) -> list[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for table in tables:
        parts = table.split(".")
        if len(parts) >= 3:
            pairs.add((parts[0], parts[1]))
    return sorted(pairs)


def _resource(checked: bool, existing: list[str] | None, note: str) -> dict:
    return {
        "checked": checked,
        "existing": existing or [],
        "note": note,
    }


def collect_inventory(
    client: object | None,
    intake: IntakeSpec,
    discovery: DiscoveryReport,
    serving_endpoint: str,
    connected: bool,
) -> dict:
    """Return ``{resources, to_create, blockers}`` after GET-ing the workspace.

    ``client`` is a ``composer.databricks.client.DatabricksClient`` (or None).
    ``connected`` gates real reads so we never fake results when offline.
    """
    live = bool(
        connected and client is not None and getattr(client, "has_real_client", lambda: False)()
    )

    resources: dict[str, dict] = {}
    to_create: list[dict] = []
    blockers: list[str] = []

    # -- serving endpoints (for the GenAI model that writes the app) ------
    endpoints = client.list_resource_names("serving_endpoints") if live else None  # type: ignore[union-attr]
    if endpoints is None:
        resources["serving_endpoints"] = _resource(
            False, None, "No verificado (requiere conexión)."
        )
        to_create.append(
            {
                "resource_type": "serving_endpoint",
                "name": serving_endpoint,
                "method": "POST",
                "reason": "Endpoint del modelo de GenAI (pendiente de verificar conexión).",
                "verified": False,
            }
        )
    else:
        resources["serving_endpoints"] = _resource(
            True, endpoints, f"{len(endpoints)} endpoint(s) encontrados."
        )
        if serving_endpoint not in endpoints:
            to_create.append(
                {
                    "resource_type": "serving_endpoint",
                    "name": serving_endpoint,
                    "method": "POST",
                    "reason": "No existe el endpoint del modelo de GenAI requerido.",
                    "verified": True,
                }
            )

    # -- tables (from the verified discovery report) ----------------------
    tables_exist = [t.name for t in discovery.tables if t.status == "exists"]
    tables_missing = [t.name for t in discovery.tables if t.status == "missing"]
    tables_unknown = [t.name for t in discovery.tables if t.status == "unknown"]
    resources["tables"] = _resource(
        live and not tables_unknown,
        tables_exist,
        (
            f"{len(tables_exist)} verificada(s), {len(tables_missing)} ausente(s)."
            if live
            else "No verificadas (requiere conexión)."
        ),
    )
    for table in tables_missing:
        blockers.append(
            f"La tabla '{table}' no existe en Unity Catalog; debe crearse/cargarse antes."
        )

    # -- genie spaces (from discovery: reuse vs create) ------------------
    genie_existing = [g.name for g in discovery.genies if g.status == "exists"]
    genie_to_create = [g.name for g in discovery.genies if g.status == "needs_creation"]
    genie_unknown = [g for g in discovery.genies if g.status == "unknown"]
    resources["genie"] = _resource(
        live and not genie_unknown,
        genie_existing,
        (
            "Búsqueda no realizada (requiere conexión)."
            if genie_unknown
            else f"{len(genie_existing)} para reutilizar, {len(genie_to_create)} por crear."
        ),
    )
    for genie in genie_to_create:
        to_create.append(
            {
                "resource_type": "genie_space",
                "name": genie if not genie.startswith("(") else "asistente sugerido",
                "method": "POST",
                "reason": "Crear el asistente Genie para el caso de uso.",
                "verified": live,
            }
        )

    # -- volumes (UC) ----------------------------------------------------
    all_volumes: list[str] = []
    volumes_checked = False
    if live:
        for catalog, schema in _catalog_schema_pairs(intake.gold_tables):
            vols = client.list_resource_names(  # type: ignore[union-attr]
                "volumes", catalog_name=catalog, schema_name=schema
            )
            if vols is not None:
                volumes_checked = True
                all_volumes.extend(vols)
    resources["volumes"] = _resource(
        volumes_checked,
        all_volumes,
        (
            f"{len(all_volumes)} volume(s) encontrados."
            if volumes_checked
            else "No verificados (requiere conexión)."
        ),
    )

    # -- knowledge assistants -------------------------------------------
    assistants = client.list_resource_names("knowledge_assistants") if live else None  # type: ignore[union-attr]
    resources["knowledge_assistants"] = _resource(
        assistants is not None,
        assistants,
        (
            f"{len(assistants)} encontrado(s)."
            if assistants is not None
            else "No verificado (requiere conexión o no disponible en este workspace)."
        ),
    )

    # -- environments ----------------------------------------------------
    environments = client.list_resource_names("environments") if live else None  # type: ignore[union-attr]
    resources["environments"] = _resource(
        environments is not None,
        environments,
        (
            f"{len(environments)} encontrado(s)."
            if environments is not None
            else "No verificado (requiere conexión o no disponible en este workspace)."
        ),
    )

    # -- the Databricks App itself (always a create/POST) ----------------
    to_create.append(
        {
            "resource_type": "databricks_app",
            "name": "business-builder-generated-app",
            "method": "POST",
            "reason": "Publicar la app generada en el workspace.",
            "verified": live,
        }
    )

    return {
        "checked": live,
        "resources": resources,
        "to_create": to_create,
        "blockers": blockers,
    }
