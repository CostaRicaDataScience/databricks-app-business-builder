# Skill: deployed_app_validation

Function: app_builder

## When to use

After generating (and optionally deploying) an app, verify it works.

## How it works

`src/composer/validate/runner.py` `validate_app(app_dir, required_scopes=...,
granted_scopes=..., app_url=..., http_get=..., logs_reader=...)` returns
`{ok, checks, failures}`:

- Static checks: requirements include databricks-sdk, app.yaml has a command,
  required OAuth scopes granted.
- Deployed checks (optional, injected): `http_get(url)` smoke test, `logs_reader()`
  error-marker triage.

## Rules

- Static checks are offline-safe and always run.
- Deployed checks run only when a URL / logs reader is provided.
- Inject `http_get` / `logs_reader` for tests; never hit the network implicitly.
