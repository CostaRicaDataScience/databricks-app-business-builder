# Databricks App Business Builder

Unified implementation of Composer + AppGen patterns for building Databricks Apps from analyst requirements.

## What it does

1. Captures structured intake from analysts.
2. Runs discovery on requested tables and genie assets.
3. Proposes metadata enrichment and records approval gates.
4. Builds an app plan with Foundation Models (Claude preferred).
5. Emits a **cascarón** (scaffold) for the Streamlit app, then optionally builds
   it out with Claude Opus (two-phase generation — see below).
6. Runs preflight checks and emits governance/tagging reports.

Artifacts are persisted under `.appgen/` for reproducibility and auditability.

## Runtime interfaces

### Guided web UI (default)

`GET /` serves a guided, plain-language flow for business analysts:

1. **Cuéntanos qué necesitas** — jargon-free questions (no internal IDs).
2. **Conectar a Databricks** — explicit connection + permission preview.
3. **Revisar y crear** — one click runs the whole pipeline and shows a
   human-readable result. Raw IDs appear only in a collapsible "Detalles
   técnicos" section.

The UI calls the single auto-run endpoint `POST /run` by default.

### FastAPI endpoints

Guided / auth (new):

- `GET /` — guided UI
- `GET /health`
- `POST /run` — **single entrypoint**: runs intake → discovery → safe autofix →
  build plan → generate, and returns a human-friendly summary
- `GET /auth/status` — Databricks connection + requested permissions
- `POST /auth/connect` — attempt connection and report status

Granular endpoints (kept for power users / scripting):

- `POST /discovery-intake`
- `POST /discovery-run`
- `POST /discovery-confirm`
- `POST /build-plan`
- `POST /generate`
- `POST /provision`
- `GET /discovery-report/{id}`
- `GET /tagging-report/{id}`
- `GET /operations/{id}`

### Composer CLI (recommended for phase workflow)

```bash
composer intake \
  --use-case "Sales KPI app" \
  --workflow "Daily refresh" \
  --style "Modern dashboard" \
  --access "Read UC + create genie + app deploy" \
  --stories "As analyst I want KPI trends" \
  --tables sales.gold_orders \
  --genies sales_assistant

composer plan
composer discover
composer propose-metadata
composer apply-metadata --approve --dry-run
composer generate-app
composer preflight
composer tag-report
```

## Install and run

```bash
uv venv
uv pip install --python .venv/bin/python -e ".[dev]"
make run
```

Open the web app:

- `http://127.0.0.1:8000/` (intake UI)
- `http://127.0.0.1:8000/docs` (API Swagger)

Tests:

```bash
pytest -q
```

## Configuration

Environment keys (see `.env.example`):

- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`
- `DATABRICKS_CONFIG_PROFILE` (alternative to host+token in `user_workspace` mode)
- `DBX_AUTH_MODE` (`user_workspace` or `service_principal`)
- `DBX_SP_CLIENT_ID`
- `DBX_SP_CLIENT_SECRET`
- `FOUNDATION_MODEL_PROVIDER`
- `FOUNDATION_MODEL_ENDPOINT` — serving endpoint used for GenAI codegen (Phase A preview)
- `PLANNER_MODEL_ENDPOINT` — separate Opus-class endpoint for the Phase B build-out (default `databricks-claude-opus-4`)
- `PREFERRED_MODEL`
- `FALLBACK_MODEL`
- `APPGEN_DIR`
- `OUTPUT_ROOT`
- `DRY_RUN_DEFAULT`
- `MCP_SERVER_URL` — Databricks MCP endpoint (`.../api/mcp/`); empty = disabled
- `MCP_GENIE_SPACE_IDS` — comma-separated Genie space ids (MCP reuse checks)
- `MCP_UC_SCHEMA` — optional Unity Catalog schema scope for MCP table checks

Databricks Apps OBO (on-behalf-of-user) needs **no env vars** — the platform
forwards the user token via request headers (see below).

## What this app can build

- Discovery-driven Databricks App implementation plans from analyst requirements.
- Metadata quality reports and enrichment proposals for requested Gold tables.
- Genie gap analysis (reuse vs create) with benchmark question scaffolding.
- Streamlit-based generated app skeletons under `OUTPUT_ROOT`.
- Preflight permission checks and governance/tagging reports.

## Getting started workflow

Default (guided, recommended):

1. Open `/`, answer the plain-language questions.
2. Use "Connect to Databricks" to verify connection + permissions.
3. Click "Crear mi app" — `POST /run` executes the full pipeline and shows a
   human-readable summary (tables found, Genies to reuse/create, generated app
   location, permissions, and what still requires your approval).

Advanced (granular, scripting):

1. Create intake (`/discovery-intake`).
2. Run discovery (`/discovery-run`) and review gaps.
3. Confirm autofix (`/discovery-confirm`) for metadata/genie actions.
4. Build plan (`/build-plan`) and generate app (`/generate`).
5. Validate permissions/tags and provision (`/provision`).

Artifacts are written under `.appgen/`:

- `requirements.yaml`
- `discovery_report.yaml`
- `metadata_quality_report.yaml`
- `app_spec.yaml`
- `final_build_plan.yaml`
- `generated_app_report.yaml`
- `cascaron_buildout_report.yaml` — manifest/plan/contracts paths + Phase B result
- `tagging_report.yaml`
- approvals in `.appgen/approvals/`

## Databricks authentication & permissions

Authentication is **explicit and visible**, not implicit. The guided UI has a
"Connect to Databricks" step before any build, and the backend exposes:

- `GET /auth/status` / `POST /auth/connect` — report `connected`, `principal`,
  `host`, `auth_mode` (`user_workspace` vs `service_principal`), `missing`
  config, a human-readable `message`, and the list of permissions being
  requested with their satisfied/missing status.

### How the connection works

The connection uses the official `databricks-sdk` via
`src/composer/databricks/client.py`:

- **user_workspace** (default): a Databricks config profile
  (`DATABRICKS_CONFIG_PROFILE`) **or** `DATABRICKS_HOST` + `DATABRICKS_TOKEN`.
- **service_principal**: `DATABRICKS_HOST` + `DBX_SP_CLIENT_ID` +
  `DBX_SP_CLIENT_SECRET` (set `DBX_AUTH_MODE=service_principal`).

When the SDK establishes a real client, `connected=true` is reported with the
authenticated principal and host (resolved via `current_user.me()`). When it
cannot (missing token/host, or a headless environment), the app reports exactly
what is missing instead of silently proceeding.

> **Interactive OAuth (U2M) is environment-dependent.** Browser-based U2M login
> may not be available in headless/server contexts. In those cases configure a
> token, a config profile, or a service principal as above. The experience
> degrades gracefully and the UI/`/auth/status` tells you precisely what to set.

### The permission-request moment

Before generation/provision, the app runs and **surfaces** the preflight
permission check (`src/composer/permissions/preflight.py`) so you see exactly
which Databricks permissions are required and whether they are satisfied. The UI
makes this the explicit "this is where we connect and request these permissions"
moment. Required permissions:

- Catalog read (Unity Catalog table/metadata discovery)
- `COMMENT ON` for metadata enrichment
- Genie create/use
- Databricks Apps create/update
- Resource tagging (governance)

Secrets are redacted by the logger and never written to logs or artifacts.

## Databricks permissions commonly required

Minimum permissions depend on workflow and auth mode:

- Catalog/table discovery: ability to read metadata in Unity Catalog.
- Metadata enrichment (`COMMENT ON`): ownership or privileges to alter table/column comments.
- Genie operations: permissions to read existing Genie spaces and create new ones when required.
- App generation/deploy: permissions for Databricks Apps create/update and related workspace resources.
- Governance/tagging: permissions to apply tags/policies to compute/pipelines/resources.

Recommended auth modes:

- `user_workspace` for user-driven local operation (token/profile based).
- `service_principal` for controlled automation/deployment pipelines.

If permissions are insufficient, preflight reports should identify missing capabilities before write actions.

## Real Databricks integration

Three capabilities make this app work against a real workspace. All three share
the auth layer and degrade gracefully so local dev and tests run with no
workspace.

### 1. Databricks Apps OBO (on-behalf-of-user) auth

When deployed inside Databricks Apps with **user authorization** enabled, the
platform forwards the signed-in user's identity and OAuth token on every request
as HTTP headers:

- `X-Forwarded-Access-Token` — the user's OAuth access token (used for OBO)
- `X-Forwarded-Email` / `X-Forwarded-User` — the user's identity

The app reads these (`src/composer/databricks/obo.py`) and builds a
**per-request** `WorkspaceClient(host=…, token=<forwarded token>)` so all
Databricks calls (discovery, Genie/MCP, serving-endpoint codegen) run with that
user's real permissions. The user token is **never cached** in a global client
and **never logged** (the logger redacts it; it never appears in `/auth/status`).

**Fallback chain** when the header is absent (local dev / not deployed as an
App): existing env/profile/service-principal config is used. The active mode is
always reported by `/auth/status` as one of:

- `databricks_app_obo` — a forwarded user token was present (OBO)
- `user_workspace` — host+token or `~/.databrickscfg` profile
- `service_principal` — `DBX_SP_CLIENT_ID` + `DBX_SP_CLIENT_SECRET`

**Enable OBO on the App side:** deploy with user authorization and configure the
scopes your workspace needs (SQL, Unity Catalog, serving endpoints, Genie) so
the platform forwards the user access token. See the commented `app.yaml`.

### 2. MCP integration (Unity Catalog / Genie via Databricks MCP)

A configurable MCP client (`src/composer/mcp/client.py`, Streamable HTTP
transport, `Authorization: Bearer <OBO-or-fallback token>`) can verify UC
tables/metadata during discovery and check real Genie spaces during reuse
decisions. **Disabled by default** (empty `MCP_SERVER_URL` → heuristic discovery,
unchanged behavior). Prefer a Databricks **Managed MCP** endpoint
(`https://<app-url>.databricksapps.com/api/mcp/` — trailing `/api/mcp/` required).
The labs `databrickslabs/mcp` UC server is deprecated. Full details and
upstream-awareness guidance: [`docs/integrations/mcp.md`](docs/integrations/mcp.md).

### 3. GenAI codegen via a serving endpoint

The generated app **skeleton** (the bootstrap `app.py` and supporting files) is
produced by a real model served via a Databricks **serving endpoint** inside the
authenticated workspace (`FOUNDATION_MODEL_ENDPOINT`, default
`databricks-claude-sonnet`), queried through the OBO/user `WorkspaceClient`
(`src/composer/llm/client.py` → `WorkspaceClient.serving_endpoints.query`). The
model output is written to disk by `src/composer/codegen/generator.py`. When no
workspace/endpoint is available (local dev, tests, headless), a **deterministic
template fallback** is used so the flow always completes.

## Two-phase generation (cascarón → build-out)

Instead of a 3-file stub, each generated app is a **cascarón** (scaffold) — the
shell of a Databricks App with everything an LLM needs to then write the full
implementation. Modeled on the OmniAgent bootstrap conventions, adapted for a
single Databricks Streamlit App.

### Phase A — deterministic cascarón (always, offline-safe)

`src/composer/codegen/cascaron.py::emit_cascaron` writes a self-describing
scaffold under `OUTPUT_ROOT/generated_<id>/`:

```
app.manifest.yaml      # SOURCE OF TRUTH: intake, discovery, resource inventory
                       #   (GET) + POST creation plan + blockers, style, refs to
                       #   gold tables / genies / serving endpoints, and a
                       #   files[] map (path, purpose, status, depends_on,
                       #   produced_by_task)
EXECUTION_PLAN.md      # agent-sized, ordered build-out plan for Claude Opus
CONTRACTS.yaml         # interface/contracts the app must honor (AppConfig,
                       #   UserAuth, DataAccess, Page, GenieClient)
app.yaml               # Databricks Apps runtime spec (command: streamlit run app/app.py)
README.md              # scaffold README (auth, scopes, system env)
spec/                  # structured inputs copied as files
  requirements.yaml  discovery_report.yaml
  resource_inventory.yaml  resource_creation_plan.yaml
app/                   # stub files with `# TODO(build-out):` + manifest cross-refs
  config.py  auth.py  data_access.py  genie.py
  pages/<page>.py ...  app.py
requirements.txt
```

No model call is required, so local dev and tests always produce a valid,
self-describing scaffold. (OmniAgent's multi-agent matrix, polyglot dependency
normalization, and security-tooling machinery are intentionally dropped.)

### Phase B — Claude Opus build-out via the AI Gateway

`src/composer/llm/client.py::LLMClient.build_out_cascaron` reads
`app.manifest.yaml` + `EXECUTION_PLAN.md` + `spec/`, then for each file whose
manifest `status: to_generate` queries a **separate planner endpoint**
(`PLANNER_MODEL_ENDPOINT`, default `databricks-claude-opus-4`), writes the
generated contents, and flips the file's status to `generated`. It runs as the
OBO user and attaches the `Databricks-Ai-Gateway-Request-Tags` header
(`{"project":"databricks-app-business-builder","phase":"build-out"}`) for usage
tracking / governance, per the
[AI Gateway query-endpoints beta doc](https://docs.databricks.com/aws/en/ai-gateway/query-endpoints-beta).

Phase B runs only when **connected** and a planner endpoint is available;
otherwise it degrades gracefully and the scaffold stays valid with every file
`to_generate`. `/run` surfaces which files were `generated` vs still
`to_generate`, plus the manifest and execution-plan paths.

### Generated-app conventions shaped by the Databricks Apps docs

What the cascarón **emits** (and documents in the generated `README.md` /
`app.manifest.yaml`) follows four Databricks Apps docs:

- **[Auth](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)** —
  the generated app uses **user authorization (OBO)**, reading
  `st.context.headers.get('x-forwarded-access-token')`; the manifest/README
  document the required OAuth scopes (`sql`, `dashboards.genie`,
  `serving.serving-endpoints`, `files.files`). App authorization
  (`DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET`) is reserved for
  shared/background actions. Tokens are never printed.
- **[System env](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)** —
  the app relies on platform-provided env vars (`DATABRICKS_HOST`,
  `DATABRICKS_APP_PORT`, …) and never hardcodes them.
- **[app.yaml runtime](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)** —
  a correct `app.yaml` is emitted (`command: ['streamlit','run','app/app.py']`,
  `env:` entries such as the SQL warehouse id).
- **[Node tutorial](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/tutorial-node)** —
  used as a structural reference only; the default emitted stack stays
  Streamlit/Python (a Node variant is optional/future).

## Archetypes (DevHub-aligned)

The builder classifies your intake into a supported archetype (mirroring the
[DevHub templates](https://developers.databricks.com/templates)) and picks a
build target. Catalog: `src/composer/archetypes/catalog.py`.

| Archetype | What it builds | Required primitives | Default target | OAuth scopes |
| --- | --- | --- | --- | --- |
| `ai_chat` | Streaming AI chat + chat history | serving_endpoint, lakebase | appkit | `serving.serving-endpoints`, `sql` |
| `crud_lakebase` | CRUD app on Lakebase Postgres | lakebase, uc_tables | appkit | `sql` |
| `genie_analytics` | Embedded Genie conversational analytics | genie, uc_tables | python | `dashboards.genie`, `sql` |
| `rag_chat` | RAG chat (pgvector + serving) | serving_endpoint, vector_search, lakebase | appkit | `serving.serving-endpoints`, `sql` |
| `dashboard` | Operational dashboard (optional Genie) | uc_tables | python | `sql`, `dashboards.genie` |

Two build targets, selected per archetype (and overridable via intake hints like
"typescript"/"streamlit"):

- `python` - FastAPI/Streamlit (default; matches the deployed builder).
- `appkit` - DevHub AppKit/TypeScript via `databricks apps init` (needs Node +
  Databricks CLI; behind a feature flag).

## Clone -> run local -> deploy

```bash
# 1) clone + install
uv venv && make install

# 2) verify local dev env (DevHub "Set Up Your Local Dev Environment")
databricks auth login --host https://<your-workspace>.cloud.databricks.com -p <profile>
curl -s localhost:8000/dev/preflight   # after the server is up (CLI + valid profile + aitools)

# 3) run locally
.venv/bin/uvicorn modules.app.main:app --reload   # http://127.0.0.1:8000

# 4) deploy as a Databricks App (bundle includes requirements.txt + app resource)
export DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
databricks bundle deploy -p <profile>
databricks bundle run business_builder -p <profile>
```

Enable **user authorization (OBO)** on the App with the scopes for your
archetype (see table). The pipeline's final `validate` step checks
requirements/`app.yaml`/scopes and proposes fixes.

## Repository structure

- `src/composer/` unified product implementation
  (`archetypes/`, `devhub/`, `codegen/` incl. `targets/`, `validate/`, ...).
- `modules/` compatibility API layer kept during migration.
- `agents/` + `skills/` agent/skill definitions (incl. the `app_builder` function).
- `.appgen/` generated artifacts and approvals.
- `examples/` end-to-end vertical examples (see `university_genie_dashboard.md`).

## Project docs

- `docs/blueprint.md`
- `docs/design.md`
- `docs/gapmaster.md`
