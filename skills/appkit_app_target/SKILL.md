# Skill: appkit_app_target

Function: app_builder

## When to use

When the chosen target is `appkit` (DevHub's TypeScript stack).

## How it works

`src/composer/codegen/targets/appkit_target.py`:

- `appkit_available()` - True only when both `databricks` CLI and `node` are on PATH.
- `plugins_for(archetype)` - maps primitives to AppKit plugins (lakebase, genie,
  model-serving, vector-search).
- `build_appkit_target(archetype, intake, app_dir, enabled, runner)` - returns a
  plan with the `databricks apps init` command; executes only when `enabled` and
  the toolchain is present. `runner` is injectable for testing.

## Rules

- Behind a feature flag; never execute when disabled or toolchain missing -
  return a plan with a `reason` instead.
- shadcn/ui on Tailwind with the Databricks palette.
