# Skill: app_log_triage

Function: app_builder

## When to use

When a deployed app misbehaves, read its logs and pinpoint the root cause.

## How it works

`validate_app(..., logs_reader=...)` scans logs for error markers:
`Traceback`, `ERROR`, `ModuleNotFoundError`, and
`more than one authorization` (the classic Databricks Apps OBO misconfig).

Provide a `logs_reader()` that shells out to `databricks apps logs` (via
`src/composer/deploy/apps.py`) or reads the captured log file.

## Rules

- Map markers to fixes (see the autofix_redeploy skill).
- `ModuleNotFoundError` -> a dependency is missing from requirements.txt.
- `more than one authorization` -> build the client with `auth_type='pat'`.
