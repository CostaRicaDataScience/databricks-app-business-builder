# Skill: lakebase_provisioning

Function: app_builder

## When to use

When an archetype needs persistence (chat history, app state, CRUD) it requires
a Lakebase (managed Postgres) instance. Use this skill to discover existing
instances and plan creation/reuse.

## How it works

- Discovery: `DatabricksClient.list_lakebase_instances()` /
  `get_lakebase_instance(name)` in `src/composer/databricks/client.py` read the
  `database` service of the SDK (https://docs.databricks.com/api/workspace/database).
  They degrade to `None` when the SDK lacks the service or we are offline.
- Planning: `collect_inventory(..., required_primitives=(... "lakebase" ...))`
  adds a `lakebase_instance` entry to `to_create` with decision `reuse` when an
  instance exists, else `create`.

## Rules

- Provisioning Lakebase costs money and takes minutes: always behind an explicit
  per-resource approval (see the approval_gating skill).
- Prefer reusing an existing instance; only create when none exists or the user
  asks for a dedicated one.
