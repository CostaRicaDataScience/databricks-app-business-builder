# Skill: agents_md_authoring

Function: app_builder

## When to use

Every generated app should ship an `AGENTS.md` that pins workspace defaults so a
coding agent (or the Phase B build-out) generates correct Databricks code.

## How it works

`src/composer/codegen/agents_md.py` `build_agents_md(manifest)` derives from the
manifest (source of truth):

- Archetype + build target + DevHub template URL
- Goal (use case, user stories)
- Workspace defaults: gold tables, catalog.schema, Genie spaces, serving
  endpoints
- Auth (OBO): header, OAuth scopes, system env, and the `auth_type='pat'` rule
  for Databricks Apps
- The Databricks design system block

The cascaron emitter writes it as `AGENTS.md` in the scaffold.

## Rules

- Derive everything from the manifest; do not invent values.
- Never include secrets/tokens.
