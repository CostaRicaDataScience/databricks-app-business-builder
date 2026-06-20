# Skill: python_app_target

Function: app_builder

## When to use

When the chosen target is `python` (FastAPI/Streamlit) - the default and the
stack of the deployed builder.

## How it works

`src/composer/codegen/targets/python_target.py` `build_python_target(archetype,
intake, has_genie=...)` returns:

- `pages` (from the archetype), `stack="streamlit-python"`
- `extra_files` - includes `app/styles.css` with the Databricks design tokens
- `needs_genie` / `needs_lakebase` / `needs_serving` flags from primitives

The orchestrator writes the extra files into the generated app and records the
plan as `target_plan.yaml`.

## Rules

- OBO everywhere (`auth_type='pat'` for the per-request client).
- Apply the design system; respect user design overrides.
