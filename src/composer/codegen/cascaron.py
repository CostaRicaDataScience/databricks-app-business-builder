"""Phase A — deterministic *cascarón* (scaffold) emitter.

A "cascarón" is the shell of a Databricks App: everything an LLM (Claude Opus,
via the Phase B build-out) needs to then write the full implementation, but with
no model call required. It is fully offline/deterministic so local dev and tests
always produce a valid, self-describing scaffold.

Modeled on the OmniAgent bootstrap conventions (manifest-as-source-of-truth, a
declarative file map, ``<TODO:>``/stub markers, a ``contracts/base-contracts``
file, and an agent-sized implementation plan) but *adapted* for a single
Databricks Streamlit App. OmniAgent's multi-agent matrix, polyglot dependency
normalization, and security-tooling machinery are intentionally dropped — they
do not fit one app.

Emitted layout (under the generated app directory)::

    app.manifest.yaml        # SOURCE OF TRUTH (intake, discovery, inventory,
                             #   POST plan, references, files[] with status)
    EXECUTION_PLAN.md        # agent-sized, ordered build-out plan for Opus
    CONTRACTS.yaml           # interface/contract definitions to honor
    app.yaml                 # Databricks Apps runtime spec
    README.md                # human-facing scaffold README
    spec/                    # structured inputs copied verbatim as files
      requirements.yaml
      discovery_report.yaml
      resource_inventory.yaml
      resource_creation_plan.yaml
    app/                     # stub files with # TODO(build-out): markers
      config.py  auth.py  data_access.py  genie.py
      pages/<page>.py ...
      app.py
    requirements.txt

The generated app's runtime conventions are shaped by the Databricks Apps docs:

* Auth (user authorization / OBO):
  https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth
* System environment variables:
  https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env
* app.yaml runtime:
  https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime
* Node tutorial (structural reference only; we emit Streamlit/Python):
  https://docs.databricks.com/aws/en/dev-tools/databricks-apps/tutorial-node
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from composer.codegen.agents_md import build_agents_md
from composer.models.blueprint import AppBlueprint, DiscoveryReport
from composer.models.intake import IntakeSpec

SCHEMA_VERSION = 1

# OAuth scopes the generated app declares for user authorization (OBO). Kept
# small and purpose-driven per the auth doc; SQL + Genie are the common pair,
# serving/files added because the app may call model endpoints and read volumes.
DEFAULT_OAUTH_SCOPES = [
    "sql",
    "dashboards.genie",
    "serving.serving-endpoints",
    "files.files",
]

# Default Databricks Apps system env vars the generated app must read (never
# hardcode) — see the system-env doc.
SYSTEM_ENV_VARS = [
    "DATABRICKS_HOST",
    "DATABRICKS_APP_PORT",
    "DATABRICKS_WORKSPACE_ID",
    "DATABRICKS_WAREHOUSE_ID",
]

TODO = "# TODO(build-out):"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(blueprint: AppBlueprint) -> str:
    return f"generated_{blueprint.blueprint_id[:8]}"


# --------------------------------------------------------------------------
# File plan — the declarative scaffold-map (path/purpose/status/deps/task)
# --------------------------------------------------------------------------

def _plan_files(blueprint: AppBlueprint, has_genie: bool) -> list[dict]:
    """Return the ordered list of target files for the build-out.

    Each entry mirrors the manifest ``files[]`` schema: ``path``, ``purpose``,
    ``status`` (always ``to_generate`` at scaffold time), ``depends_on`` and
    ``produced_by_task``.
    """
    pages = list(blueprint.pages) or ["home"]
    entries: list[dict] = [
        {
            "path": "app/config.py",
            "purpose": (
                "Read Databricks Apps system env vars (DATABRICKS_HOST, "
                "DATABRICKS_APP_PORT, DATABRICKS_WAREHOUSE_ID, ...). Never "
                "hardcode them."
            ),
            "depends_on": [],
        },
        {
            "path": "app/auth.py",
            "purpose": (
                "Resolve the per-request user identity via on-behalf-of-user "
                "(OBO): read 'x-forwarded-access-token' from request headers."
            ),
            "depends_on": ["app/config.py"],
        },
        {
            "path": "app/data_access.py",
            "purpose": (
                "Unity Catalog / SQL data access for the gold tables, executed "
                "as the OBO user against the configured SQL warehouse."
            ),
            "depends_on": ["app/config.py", "app/auth.py"],
        },
    ]
    if has_genie:
        entries.append(
            {
                "path": "app/genie.py",
                "purpose": (
                    "Genie space integration: send the analyst's question to "
                    "the referenced Genie space and render the answer."
                ),
                "depends_on": ["app/config.py", "app/auth.py"],
            }
        )
    page_deps = ["app/data_access.py"] + (["app/genie.py"] if has_genie else [])
    for page in pages:
        entries.append(
            {
                "path": f"app/pages/{page}.py",
                "purpose": f"Render the '{page}' page using the data-access layer.",
                "depends_on": page_deps,
            }
        )
    entries.append(
        {
            "path": "app/app.py",
            "purpose": (
                "Streamlit entrypoint: page routing, OBO header read, layout "
                "and style tokens. This is the app.yaml command target."
            ),
            "depends_on": ["app/config.py", "app/auth.py"]
            + [f"app/pages/{p}.py" for p in pages],
        }
    )
    entries.append(
        {
            "path": "requirements.txt",
            "purpose": "Python runtime dependencies for the Databricks App.",
            "depends_on": [],
        }
    )
    for idx, entry in enumerate(entries, start=1):
        entry["status"] = "to_generate"
        entry["produced_by_task"] = f"T{idx}"
    return entries


# --------------------------------------------------------------------------
# Manifest (source of truth)
# --------------------------------------------------------------------------

def _build_manifest(
    *,
    blueprint: AppBlueprint,
    intake: IntakeSpec,
    discovery: DiscoveryReport | None,
    inventory: dict | None,
    codegen_endpoint: str,
    planner_endpoint: str,
    file_plan: list[dict],
    archetype: dict | None = None,
) -> dict:
    genie_refs = [g.name for g in (discovery.genies if discovery else [])]
    genie_refs += [g for g in intake.existing_genies if g not in genie_refs]
    discovery_block = None
    if discovery is not None:
        discovery_block = {
            "summary": discovery.summary,
            "tables": [
                {"name": t.name, "status": t.status} for t in discovery.tables
            ],
            "genies": [
                {"name": g.name, "status": g.status} for g in discovery.genies
            ],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "databricks-app-cascaron",
        "archetype": archetype or {"id": None, "target": "python", "devhub_url": None},
        "project": {
            "name": "business-builder-generated-app",
            "slug": _slug(blueprint),
            "blueprint_id": blueprint.blueprint_id,
            "generated_at": _now_iso(),
            "generated_by": "databricks-app-business-builder · cascarón emitter (Phase A)",
        },
        "runtime": {
            "stack": "streamlit-python",
            "entrypoint": "app/app.py",
            "command": ["streamlit", "run", "app/app.py"],
            "databricks_apps": {
                # User authorization (OBO): read x-forwarded-access-token so all
                # workspace calls run as the signed-in user.
                # https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth
                "authorization": "user_authorization_obo",
                "obo_header": "x-forwarded-access-token",
                "required_oauth_scopes": list(DEFAULT_OAUTH_SCOPES),
                # App authorization (service principal) only for shared/background
                # actions — DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET.
                "app_authorization": (
                    "DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET — shared "
                    "or background actions only; user actions use OBO."
                ),
                # https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env
                "system_env": list(SYSTEM_ENV_VARS),
            },
        },
        "intake": {
            "primary_use_case_description": intake.primary_use_case_description,
            "user_stories": list(intake.user_stories),
            "gold_tables": list(intake.gold_tables),
            "existing_genies": list(intake.existing_genies),
            "workflow_requirements": intake.workflow_requirements,
            "style_preferences": intake.style_preferences,
            "access_requirements": intake.access_requirements,
        },
        "discovery": discovery_block,
        "resources": {
            "inventory": (inventory or {}).get("resources", {}),
            "to_create": (inventory or {}).get("to_create", []),
            "blockers": (inventory or {}).get("blockers", []),
            "checked": (inventory or {}).get("checked", False),
        },
        "references": {
            "gold_tables": list(intake.gold_tables),
            "genie_spaces": genie_refs,
            "serving_endpoints": {
                "codegen": codegen_endpoint,
                "planner": planner_endpoint,
            },
        },
        "style": {"preferences": intake.style_preferences, "tokens": blueprint.style_tokens},
        "build_out": {
            # Phase B fills the `to_generate` files and flips their status.
            "planner_endpoint": planner_endpoint,
            "phase": "not_started",
            "execution_plan": "EXECUTION_PLAN.md",
            "contracts": "CONTRACTS.yaml",
        },
        "files": file_plan,
    }


# --------------------------------------------------------------------------
# EXECUTION_PLAN.md — agent-sized ordered plan for the build-out LLM
# --------------------------------------------------------------------------

def _build_execution_plan(manifest: dict, file_plan: list[dict]) -> str:
    project = manifest["project"]
    intake = manifest["intake"]
    runtime = manifest["runtime"]
    lines: list[str] = []
    lines.append(f"# Execution Plan — {project['name']}")
    lines.append("")
    lines.append(
        f"> Cascarón (Phase A) generated {project['generated_at']} · "
        f"blueprint `{project['blueprint_id']}`"
    )
    lines.append("")
    lines.append(
        "This is the agent-sized build-out plan for **Phase B (Claude Opus via "
        "the Databricks AI Gateway)**. `app.manifest.yaml` is the source of "
        "truth; this plan and `CONTRACTS.yaml` tell you *what* each file must do "
        "and *in what order*. Implement every file whose manifest "
        "`status: to_generate` and honor the contracts."
    )
    lines.append("")
    lines.append("## Goal")
    lines.append("")
    lines.append(f"- **Use case:** {intake['primary_use_case_description']}")
    if intake["user_stories"]:
        lines.append("- **User stories:**")
        for story in intake["user_stories"]:
            lines.append(f"  - {story}")
    lines.append(f"- **Gold tables:** {', '.join(intake['gold_tables']) or '(none)'}")
    lines.append(f"- **Style:** {intake['style_preferences'] or '(default)'}")
    lines.append("")
    lines.append("## Runtime conventions (Databricks Apps)")
    lines.append("")
    lines.append(
        f"- **Entrypoint:** `{runtime['entrypoint']}` · "
        f"**command:** `{' '.join(runtime['command'])}`"
    )
    lines.append(
        "- **Auth:** user authorization (OBO). Read "
        "`st.context.headers.get('x-forwarded-access-token')` and build a "
        "per-request `WorkspaceClient`; never print tokens. "
        "([auth doc](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth))"
    )
    scopes = ", ".join(runtime["databricks_apps"]["required_oauth_scopes"])
    lines.append(f"- **Required OAuth scopes:** {scopes}")
    env = ", ".join(runtime["databricks_apps"]["system_env"])
    lines.append(
        f"- **System env (read, do not hardcode):** {env} "
        "([system-env doc](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env))"
    )
    lines.append("")
    lines.append("## Resources")
    res = manifest["resources"]
    if res.get("to_create"):
        lines.append("")
        lines.append("**To create (POST) — stub, do not assume these exist:**")
        for item in res["to_create"]:
            lines.append(
                f"- `{item.get('resource_type')}` {item.get('name')} — "
                f"{item.get('reason')}"
            )
    if res.get("blockers"):
        lines.append("")
        lines.append("**Blockers:**")
        for blocker in res["blockers"]:
            lines.append(f"- {blocker}")
    lines.append("")
    lines.append("## Build-out tasks (ordered)")
    lines.append("")
    for entry in file_plan:
        deps = ", ".join(entry["depends_on"]) or "(none)"
        lines.append(
            f"### {entry['produced_by_task']} · `{entry['path']}`"
        )
        lines.append("")
        lines.append(f"- **Responsibility:** {entry['purpose']}")
        lines.append(f"- **Depends on:** {deps}")
        lines.append(f"- **Status:** {entry['status']}")
        lines.append(
            f"- **Manifest entry:** `files[path={entry['path']}]` in "
            "`app.manifest.yaml`."
        )
        lines.append("")
    lines.append("## Definition of done")
    lines.append("")
    lines.append(
        "- Every `to_generate` file is implemented and its manifest status is "
        "`generated`."
    )
    lines.append("- The app boots with `" + " ".join(runtime["command"]) + "`.")
    lines.append("- All workspace calls run as the OBO user; no tokens are logged.")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CONTRACTS.yaml — adapted from OmniAgent base-contracts for a single app
# --------------------------------------------------------------------------

def _build_contracts(has_genie: bool) -> dict:
    contracts = [
        {
            "name": "AppConfig",
            "module": "app/config.py",
            "description": "Typed access to Databricks Apps system env vars.",
            "operations": [
                "host() -> str",
                "warehouse_id() -> str | None",
                "app_port() -> int",
            ],
        },
        {
            "name": "UserAuth",
            "module": "app/auth.py",
            "description": (
                "Per-request on-behalf-of-user identity from forwarded headers."
            ),
            "operations": [
                "access_token(headers) -> str | None  # x-forwarded-access-token",
                "workspace_client(headers) -> WorkspaceClient  # scoped to the user",
            ],
        },
        {
            "name": "DataAccess",
            "module": "app/data_access.py",
            "description": "Read gold tables via the SQL warehouse as the OBO user.",
            "operations": [
                "query(sql: str) -> DataFrame",
                "table(name: str, limit: int) -> DataFrame",
            ],
        },
        {
            "name": "Page",
            "module": "app/pages/*",
            "description": "A Streamlit page rendered by the entrypoint router.",
            "operations": ["render() -> None"],
        },
    ]
    if has_genie:
        contracts.append(
            {
                "name": "GenieClient",
                "module": "app/genie.py",
                "description": "Ask a referenced Genie space and return its answer.",
                "operations": [
                    "ask(space_id: str, question: str) -> GenieAnswer",
                ],
            }
        )
    return {"version": SCHEMA_VERSION, "contracts": contracts}


# --------------------------------------------------------------------------
# app.yaml — Databricks Apps runtime spec
# --------------------------------------------------------------------------

def _build_app_yaml(manifest: dict, inventory: dict | None) -> str:
    # https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime
    command = manifest["runtime"]["command"]
    scopes = manifest["runtime"]["databricks_apps"]["required_oauth_scopes"]
    lines = [
        "# Databricks Apps runtime spec.",
        "# https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime",
        "name: business-builder-generated-app",
        "command:",
    ]
    for part in command:
        lines.append(f"  - {part!r}")
    lines.append("env:")
    # DATABRICKS_HOST / DATABRICKS_APP_PORT are provided by the platform; we only
    # surface app-specific config (e.g. the SQL warehouse id) here.
    lines.append("  # Provided by the Databricks Apps platform: DATABRICKS_HOST,")
    lines.append("  # DATABRICKS_APP_PORT. Do not hardcode them (system-env doc).")
    lines.append("  - name: 'DATABRICKS_WAREHOUSE_ID'")
    lines.append("    value: '<TODO: set your SQL warehouse id>'")
    lines.append("# User authorization (OBO) — required OAuth scopes:")
    for scope in scopes:
        lines.append(f"#   - {scope}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Stub files (app/) with TODO(build-out) markers + manifest cross-refs
# --------------------------------------------------------------------------

def _requirements_txt() -> str:
    return (
        "streamlit\n"
        "databricks-sdk\n"
        "databricks-sql-connector\n"
        "pandas\n"
    )


def _entrypoint_stub(entry: dict, manifest: dict) -> str:
    pages = manifest["runtime"].get("pages") or [
        f["path"].split("/")[-1][:-3]
        for f in manifest["files"]
        if f["path"].startswith("app/pages/")
    ]
    scopes = ", ".join(manifest["runtime"]["databricks_apps"]["required_oauth_scopes"])
    return (
        '"""Streamlit entrypoint (cascarón stub).\n\n'
        f"See app.manifest.yaml -> files[path={entry['path']}] and EXECUTION_PLAN.md "
        f"({entry['produced_by_task']}).\n"
        "Auth: user authorization (OBO) — read x-forwarded-access-token.\n"
        "https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth\n"
        f"Required OAuth scopes: {scopes}.\n"
        '"""\n\n'
        "import streamlit as st\n\n"
        f"{TODO} implement page routing + layout per EXECUTION_PLAN.md "
        f"({entry['produced_by_task']}).\n"
        f"# Depends on: {', '.join(entry['depends_on']) or '(none)'}.\n"
        "# OBO: read the forwarded user token (never print it):\n"
        "#   token = st.context.headers.get('x-forwarded-access-token')\n"
        f"# Pages to route: {', '.join(pages) or '(none)'}.\n\n"
        "st.title('TODO: build-out pending')\n"
        "st.info('This app is a cascarón. Phase B (Claude Opus) fills the "
        "to_generate files listed in app.manifest.yaml.')\n"
    )


def _module_stub(entry: dict) -> str:
    return (
        f'"""{entry["purpose"]}\n\n'
        f"Cascarón stub — see app.manifest.yaml -> files[path={entry['path']}]\n"
        f"and EXECUTION_PLAN.md ({entry['produced_by_task']}).\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        f"{TODO} implement {entry['path']} per EXECUTION_PLAN.md "
        f"({entry['produced_by_task']}).\n"
        f"# Depends on: {', '.join(entry['depends_on']) or '(none)'}.\n"
    )


def _stub_for(entry: dict, manifest: dict) -> str:
    path = entry["path"]
    if path == "requirements.txt":
        return _requirements_txt()
    if path == "app/app.py":
        return _entrypoint_stub(entry, manifest)
    return _module_stub(entry)


# --------------------------------------------------------------------------
# README for the generated scaffold
# --------------------------------------------------------------------------

def _build_readme(manifest: dict) -> str:
    runtime = manifest["runtime"]
    scopes = ", ".join(runtime["databricks_apps"]["required_oauth_scopes"])
    env = ", ".join(runtime["databricks_apps"]["system_env"])
    return (
        f"# {manifest['project']['name']}\n\n"
        "This is a **cascarón** (scaffold) generated by the Databricks App "
        "Business Builder. It is self-describing: `app.manifest.yaml` is the "
        "source of truth, `EXECUTION_PLAN.md` is the agent-sized build-out plan, "
        "and `CONTRACTS.yaml` lists the interfaces to honor.\n\n"
        "## Two-phase generation\n\n"
        "1. **Phase A (this scaffold)** — deterministic, offline. Emits the "
        "manifest, plan, contracts, `spec/`, and `app/` stub files marked with "
        f"`{TODO}`.\n"
        "2. **Phase B (build-out)** — Claude Opus, via the Databricks AI "
        "Gateway, fills every file whose manifest `status: to_generate` and "
        "flips it to `generated`.\n\n"
        "## Runtime\n\n"
        f"- **Stack:** {runtime['stack']}\n"
        f"- **Entrypoint:** `{runtime['entrypoint']}`\n"
        f"- **Command:** `{' '.join(runtime['command'])}`\n\n"
        "## Auth (user authorization / OBO)\n\n"
        "This app uses **user authorization (on-behalf-of-user)**. The platform "
        "forwards the signed-in user's OAuth token on every request; read it via "
        "`st.context.headers.get('x-forwarded-access-token')` (Streamlit) and "
        "build a per-request `WorkspaceClient`. **Never print or log the token.** "
        "Use app authorization (`DATABRICKS_CLIENT_ID` / "
        "`DATABRICKS_CLIENT_SECRET`) only for shared/background actions.\n\n"
        f"- **Required OAuth scopes:** {scopes}\n"
        f"- **System env (read, never hardcode):** {env}\n\n"
        "Docs: "
        "[auth](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth), "
        "[system-env](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env), "
        "[app-runtime](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime).\n"
    )


# --------------------------------------------------------------------------
# Public entrypoint
# --------------------------------------------------------------------------

def _safe_write(base: Path, rel_path: str, body: str) -> str | None:
    """Write ``body`` to ``base/rel_path``, refusing paths that escape ``base``."""
    target = (base / rel_path).resolve()
    base_resolved = base.resolve()
    if base_resolved != target and base_resolved not in target.parents:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return str(target)


def emit_cascaron(
    *,
    app_dir: str | Path,
    blueprint: AppBlueprint,
    intake: IntakeSpec,
    discovery: DiscoveryReport | None = None,
    inventory: dict | None = None,
    codegen_endpoint: str = "databricks-claude-sonnet",
    planner_endpoint: str = "databricks-claude-opus-4",
    archetype: dict | None = None,
) -> dict:
    """Emit the deterministic cascarón scaffold into ``app_dir``.

    Returns a summary dict with the manifest/plan/contracts paths, the full list
    of written scaffold files, and the list of files still ``to_generate`` (what
    Phase B will fill).
    """
    base = Path(app_dir)
    base.mkdir(parents=True, exist_ok=True)

    has_genie = bool(
        intake.existing_genies or (discovery and discovery.genies)
    )
    file_plan = _plan_files(blueprint, has_genie)
    manifest = _build_manifest(
        blueprint=blueprint,
        intake=intake,
        discovery=discovery,
        inventory=inventory,
        codegen_endpoint=codegen_endpoint,
        planner_endpoint=planner_endpoint,
        file_plan=file_plan,
        archetype=archetype,
    )

    written: list[str] = []

    def _record(path: str | None) -> None:
        if path:
            written.append(path)

    # 1) Manifest (source of truth) — write first so other docs can reference it.
    manifest_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    manifest_path = _safe_write(base, "app.manifest.yaml", manifest_yaml)
    _record(manifest_path)

    # 2) EXECUTION_PLAN.md
    plan_path = _safe_write(
        base, "EXECUTION_PLAN.md", _build_execution_plan(manifest, file_plan)
    )
    _record(plan_path)

    # 3) CONTRACTS.yaml
    contracts_yaml = yaml.safe_dump(
        _build_contracts(has_genie), sort_keys=False, allow_unicode=True
    )
    contracts_path = _safe_write(base, "CONTRACTS.yaml", contracts_yaml)
    _record(contracts_path)

    # 4) spec/ — structured inputs copied as files.
    spec_payloads = {
        "spec/requirements.yaml": intake.model_dump(mode="json"),
        "spec/discovery_report.yaml": (
            discovery.model_dump(mode="json") if discovery is not None else {}
        ),
        "spec/resource_inventory.yaml": (inventory or {}).get("resources", {}),
        "spec/resource_creation_plan.yaml": {
            "to_create": (inventory or {}).get("to_create", []),
            "blockers": (inventory or {}).get("blockers", []),
        },
    }
    for rel, payload in spec_payloads.items():
        _record(
            _safe_write(
                base, rel, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
            )
        )

    # 5) app.yaml + README.md + AGENTS.md (workspace defaults for coding agents)
    _record(_safe_write(base, "app.yaml", _build_app_yaml(manifest, inventory)))
    _record(_safe_write(base, "README.md", _build_readme(manifest)))
    _record(_safe_write(base, "AGENTS.md", build_agents_md(manifest)))

    # 6) Stub files (app/...) with TODO(build-out) markers.
    for entry in file_plan:
        _record(_safe_write(base, entry["path"], _stub_for(entry, manifest)))

    return {
        "output_path": str(base),
        "manifest_path": manifest_path,
        "execution_plan_path": plan_path,
        "contracts_path": contracts_path,
        "scaffold_files": sorted(written),
        "files_to_generate": [e["path"] for e in file_plan],
    }
