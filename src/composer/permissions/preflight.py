"""Preflight permission checks before writes/deploy."""

from __future__ import annotations

# Maps internal capability keys to user-facing permission descriptions. This is
# the single source of truth for "which Databricks permissions do we request and
# why" so the UI can surface the exact moment and scope of permission requests.
PERMISSION_CATALOG: dict[str, dict[str, str]] = {
    "read_catalog": {
        "label": "Lectura de catálogo (Unity Catalog)",
        "why": "Descubrir tus tablas Gold y su metadata.",
    },
    "comment_on": {
        "label": "Comentar tablas y columnas (COMMENT ON)",
        "why": "Mejorar descripciones de datos cuando faltan.",
    },
    "manage_genie": {
        "label": "Crear y usar asistentes Genie",
        "why": "Reutilizar o crear el asistente de datos de la app.",
    },
    "create_databricks_app": {
        "label": "Crear/actualizar Databricks Apps",
        "why": "Publicar la app generada en tu workspace.",
    },
    "tag_resources": {
        "label": "Etiquetar recursos (governance/tagging)",
        "why": "Aplicar tags de gobernanza a los recursos creados.",
    },
}

# Default set of permissions this product requests for an end-to-end run.
DEFAULT_REQUIRED_CAPABILITIES: tuple[str, ...] = (
    "read_catalog",
    "comment_on",
    "manage_genie",
    "create_databricks_app",
    "tag_resources",
)


def run_preflight(access_requirements: str, capabilities: dict[str, bool]) -> dict:
    missing = [cap for cap, allowed in capabilities.items() if not allowed]
    return {
        "required_access": access_requirements,
        "ok": not missing,
        "missing_capabilities": missing,
    }


def summarize_permissions(
    capabilities: dict[str, bool],
    required: tuple[str, ...] = DEFAULT_REQUIRED_CAPABILITIES,
) -> list[dict]:
    """Return a human-readable list of requested permissions with status.

    Each item: ``{key, label, why, satisfied}``. Unknown capabilities are still
    reported so nothing is silently dropped.
    """
    summary: list[dict] = []
    for key in required:
        meta = PERMISSION_CATALOG.get(
            key, {"label": key, "why": "Permiso requerido."}
        )
        summary.append(
            {
                "key": key,
                "label": meta["label"],
                "why": meta["why"],
                "satisfied": bool(capabilities.get(key, False)),
            }
        )
    return summary
