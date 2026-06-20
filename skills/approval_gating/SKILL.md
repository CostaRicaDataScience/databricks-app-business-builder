# Skill: approval_gating

Function: app_builder

## When to use

Whenever a write/provisioning action is about to run. No resource is created or
reused without an explicit decision.

## How it works

`src/composer/core/approvals.py` `ApprovalGate`:

- `set_decision(resource_id, decision)` where decision is `create`|`reuse`|`skip`.
- `decision_for(resource_id, default)` returns the effective decision.
- `apply_decisions(to_create)` filters out `skip` items and annotates the rest
  with their effective decision so provisioning only acts on approved resources.
- `ensure_allowed(action, approved)` / `record(...)` keep an audit trail under
  `.appgen/approvals/`.

## Rules

- Default to the resource's own `decision` from the inventory; the user can flip
  it per resource in the UI.
- Costly resources (Lakebase, Genie, serving endpoints, publishing the app)
  must be explicitly approved; never auto-create them.
