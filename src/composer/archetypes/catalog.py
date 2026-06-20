"""Catalog of supported app archetypes (mirrors DevHub cookbooks/recipes).

Each archetype declares the Databricks *primitives* it needs (so the resource
inventory + POST plan can be derived deterministically), a default build target,
the canonical DevHub template URL it maps to, and keyword hints used by the
rule-based classifier.

Primitive vocabulary (kept small and explicit):
    uc_tables       Unity Catalog tables (gold layer)
    genie           AI/BI Genie space (conversational analytics)
    serving_endpoint Model Serving / AI Gateway endpoint (GenAI)
    lakebase        Managed Postgres (persistence / chat history / app state)
    vector_search   Vector index for retrieval (RAG)
    volume          Unity Catalog volume (files)
"""

from __future__ import annotations

from dataclasses import dataclass

# Build targets we can generate. "python" = FastAPI/Streamlit (default, matches
# the already-deployed app). "appkit" = DevHub AppKit/TypeScript scaffold.
TARGET_PYTHON = "python"
TARGET_APPKIT = "appkit"
VALID_TARGETS = (TARGET_PYTHON, TARGET_APPKIT)


@dataclass(frozen=True, slots=True)
class Archetype:
    id: str
    title: str
    devhub_url: str
    summary: str
    required_primitives: tuple[str, ...]
    optional_primitives: tuple[str, ...] = ()
    default_target: str = TARGET_PYTHON
    ui_pages: tuple[str, ...] = ("home",)
    # Keyword hints (lowercase, EN + ES) used by the rule-based classifier.
    keywords: tuple[str, ...] = ()


ARCHETYPES: dict[str, Archetype] = {
    "ai_chat": Archetype(
        id="ai_chat",
        title="AI Chat App",
        devhub_url="https://developers.databricks.com/templates/ai-chat-app",
        summary=(
            "Streaming AI chat backed by Model Serving (AI Gateway) with "
            "Lakebase-persisted chat history."
        ),
        required_primitives=("serving_endpoint", "lakebase"),
        optional_primitives=("genie", "uc_tables"),
        default_target=TARGET_APPKIT,
        ui_pages=("chat",),
        keywords=(
            "chat",
            "chatbot",
            "conversar",
            "conversa",
            "asistente",
            "assistant",
            "pregunta",
            "preguntar",
            "mensaje",
            "streaming",
        ),
    ),
    "crud_lakebase": Archetype(
        id="crud_lakebase",
        title="App with Lakebase",
        devhub_url="https://developers.databricks.com/templates/app-with-lakebase",
        summary=(
            "Databricks App with Lakebase Postgres for persistent storage: "
            "schema setup and full CRUD API routes."
        ),
        required_primitives=("lakebase", "uc_tables"),
        optional_primitives=(),
        default_target=TARGET_APPKIT,
        ui_pages=("home", "records"),
        keywords=(
            "crud",
            "registro",
            "registros",
            "formulario",
            "form",
            "guardar",
            "editar",
            "create",
            "update",
            "delete",
            "persistencia",
            "persistir",
        ),
    ),
    "genie_analytics": Archetype(
        id="genie_analytics",
        title="Genie Analytics App",
        devhub_url="https://developers.databricks.com/templates/genie-analytics-app",
        summary=(
            "Minimal Databricks App with AI/BI Genie conversational analytics "
            "embedded: ask natural-language questions over your data."
        ),
        required_primitives=("genie", "uc_tables"),
        optional_primitives=("serving_endpoint",),
        default_target=TARGET_PYTHON,
        ui_pages=("home", "genie"),
        keywords=(
            "genie",
            "conversar con los datos",
            "natural language",
            "lenguaje natural",
            "analitica conversacional",
            "analytics",
            "preguntar a los datos",
            "embebido",
            "embed",
        ),
    ),
    "rag_chat": Archetype(
        id="rag_chat",
        title="RAG Chat App",
        devhub_url="https://developers.databricks.com/templates/rag-chat",
        summary=(
            "Retrieval-Augmented Generation chat with pgvector retrieval from "
            "Lakebase, Model Serving generation, and chat history."
        ),
        required_primitives=("serving_endpoint", "vector_search", "lakebase"),
        optional_primitives=("uc_tables",),
        default_target=TARGET_APPKIT,
        ui_pages=("chat",),
        keywords=(
            "rag",
            "retrieval",
            "documentos",
            "documents",
            "busqueda",
            "search",
            "knowledge",
            "conocimiento",
            "vector",
            "embeddings",
        ),
    ),
    "dashboard": Archetype(
        id="dashboard",
        title="Operational Dashboard",
        devhub_url="https://developers.databricks.com/templates/operational-data-analytics",
        summary=(
            "Operational dashboard with KPIs and analytics over gold tables, "
            "optionally with an embedded Genie chat panel."
        ),
        required_primitives=("uc_tables",),
        optional_primitives=("genie", "serving_endpoint"),
        default_target=TARGET_PYTHON,
        ui_pages=("home", "metrics"),
        keywords=(
            "dashboard",
            "tablero",
            "kpi",
            "kpis",
            "metricas",
            "métricas",
            "metrics",
            "reporte",
            "report",
            "visualizar",
            "numeros",
            "números",
            "avances",
            "indicadores",
            "director",
            "directores",
        ),
    ),
}

DEFAULT_ARCHETYPE_ID = "dashboard"


def list_archetypes() -> list[Archetype]:
    return list(ARCHETYPES.values())


def get_archetype(archetype_id: str | None) -> Archetype | None:
    if not archetype_id:
        return None
    return ARCHETYPES.get(archetype_id)


def default_archetype() -> Archetype:
    return ARCHETYPES[DEFAULT_ARCHETYPE_ID]
