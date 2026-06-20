# Skill: local_dev_verification

Function: app_builder

## When to use

Before running any CLI/deploy step locally - a misconfigured CLI profile fails
immediately and looks like a bug.

## How it works

`src/composer/deploy/local_dev.py` `local_dev_preflight(runner=None)` returns:

- `cli_installed`, `cli_path`, `cli_version`
- `profiles` (`[{name, valid}]`) and `has_valid_profile`
- `aitools_version` (agent skills)
- `ready` - True when the CLI is installed and a valid profile exists

Exposed at `GET /dev/preflight` for local dev. `runner` is injectable for tests.

## Target state (DevHub "Set Up Your Local Dev Environment")

- Databricks CLI >= 1.0 on PATH
- `databricks auth profiles` shows `Valid: YES`
- `databricks current-user me` returns your identity

## Rules

- Local dev only; a deployed Databricks App has no CLI (returns cli_installed=False).
- Best-effort and non-blocking; never raise.
