# Skill: archetype_catalog

Function: app_builder

## When to use

Use this skill whenever you need to know which app archetypes the builder
supports, what Databricks primitives each one requires, and which DevHub
template it maps to.

## What it provides

The catalog lives in `src/composer/archetypes/catalog.py`. Each `Archetype`
declares:

- `id`, `title`, `summary`
- `devhub_url` — the canonical DevHub cookbook/recipe it mirrors
- `required_primitives` / `optional_primitives` — from the vocabulary
  `uc_tables, genie, serving_endpoint, lakebase, vector_search, volume`
- `default_target` — `python` (FastAPI/Streamlit) or `appkit` (TypeScript)
- `ui_pages`, `keywords`

Supported archetypes: `ai_chat`, `crud_lakebase`, `genie_analytics`,
`rag_chat`, `dashboard`.

## How to use

- `list_archetypes()`, `get_archetype(id)`, `default_archetype()`.
- The required primitives drive the resource inventory + POST plan (Phase 2) and
  the provisioning steps (Phase 4). Never assume a primitive exists; always
  surface create-vs-reuse.
