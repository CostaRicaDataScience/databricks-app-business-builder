# Skill: resource_inventory

Function: app_builder

## When to use

Before generating or provisioning anything, take stock of the workspace and map
exactly what must be created vs reused.

## How it works

`src/composer/databricks/inventory.py` `collect_inventory(...)` performs
best-effort GETs (serving endpoints, UC tables, Genie spaces, volumes, knowledge
assistants, environments, and Lakebase when the archetype needs it) and returns:

- `resources` — per-family `{checked, existing, note}`
- `to_create` — POST/REUSE plan; each item has `resource_id`, `decision`
  (`create`|`reuse`|`skip`), `verified`
- `blockers` — hard stops (e.g. a missing UC table)
- `checked` — whether reads were live

## Rules

- Pass the archetype's `required_primitives + optional_primitives` so optional
  reads (e.g. Lakebase) only run when needed.
- When offline (`connected=False`) everything is reported `checked=False` and the
  POST plan is marked `verified=False`; never fabricate results.
