# Example: University director dashboard with embedded Genie

A complete vertical that exercises the `genie_analytics` archetype end-to-end:
an operational dashboard for university directors with an embedded Genie chat so
they can ask natural-language questions over the gold tables.

## Intake (what you type in Step 1)

- **What do you want to achieve?**
  App para los directores de la universidad.
- **What should users be able to do?**
  Revisar semanalmente los números y avances de investigación; conversar con un
  Genie embebido sobre estudiantes e investigación.
- **Which data (tables)?**
  `serverless_stable_ys5bgd_catalog.pontificia_universidad_catolica_de_chile_gold.gold_estudiante_360_genie`,
  `serverless_stable_ys5bgd_catalog.pontificia_universidad_catolica_de_chile_gold.gold_research_acceleration_cockpit`
- **Existing assistant?**
  "No estoy seguro, quiero que busques." (the builder searches your Genie spaces)
- **Update cadence / approver?** Semanalmente.
- **Who uses it / data access?** Los directores de la universidad.
- **Look & feel?** Estilo liquid glass (Apple 2026) on the Databricks palette.

## Expected classification

- **Archetype:** `genie_analytics` (a Genie reference + "conversar con los datos").
- **Target:** `python` (Streamlit) by default.
- **Required primitives:** `genie`, `uc_tables`; optional `serving_endpoint`.

## What the pipeline produces

1. `classify` -> Genie Analytics App (target python)
2. `discovery` -> verifies the two gold tables and searches Genie spaces
3. `resources` -> GET inventory + POST plan (reuse vs create Genie; per-resource
   approval)
4. prompt design -> `AGENTS.md` + Databricks design system + DevHub template
5. cascaron (Phase A) -> manifest, EXECUTION_PLAN, CONTRACTS, `app/` stubs incl.
   a Genie panel page; `app/styles.css` with the brand palette
6. build-out (Phase B, Opus) -> fills the stubs when connected
7. `validate` -> requirements/app.yaml/scopes checks + fixes

## Run it locally

```bash
uv venv && make install
.venv/bin/uvicorn modules.app.main:app --reload
# open http://127.0.0.1:8000 and paste the intake above
```

## OAuth scopes this archetype needs

`sql`, `dashboards.genie`, `serving.serving-endpoints` (if codegen/serving),
`files.files` (if reading volumes).
