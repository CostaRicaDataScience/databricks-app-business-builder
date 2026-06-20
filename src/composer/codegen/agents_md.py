"""Emit AGENTS.md for the generated app (Phase 3 - prompt design).

Mirrors DevHub's "Onboard Your Coding Agent": pin the workspace defaults so any
coding agent (including the Phase B build-out) generates correct Databricks code
instead of guessing. Derives everything from the manifest (source of truth).
"""

from __future__ import annotations

from composer.codegen.design_system import design_system_markdown


def _catalog_schema_pairs(tables: list[str]) -> list[str]:
    pairs: list[str] = []
    seen: set[str] = set()
    for table in tables:
        parts = table.split(".")
        if len(parts) >= 2:
            key = f"{parts[0]}.{parts[1]}"
            if key not in seen:
                seen.add(key)
                pairs.append(key)
    return pairs


def build_agents_md(manifest: dict) -> str:
    archetype = manifest.get("archetype") or {}
    intake = manifest.get("intake") or {}
    runtime = manifest.get("runtime") or {}
    dbx = runtime.get("databricks_apps") or {}
    references = manifest.get("references") or {}
    target = archetype.get("target", "python")

    gold_tables = list(intake.get("gold_tables") or [])
    schemas = _catalog_schema_pairs(gold_tables)
    scopes = dbx.get("required_oauth_scopes") or []
    system_env = dbx.get("system_env") or []
    serving = references.get("serving_endpoints") or {}
    genie_spaces = references.get("genie_spaces") or []

    lines: list[str] = []
    lines.append(f"# AGENTS.md - {manifest.get('project', {}).get('name', 'app')}")
    lines.append("")
    lines.append(
        "Workspace defaults and conventions for any coding agent working on this "
        "app (including the Phase B build-out). Treat this file as ground truth."
    )
    lines.append("")
    lines.append("## Archetype")
    lines.append(f"- **Type:** {archetype.get('title') or archetype.get('id') or 'n/a'}")
    lines.append(f"- **Build target:** {target}")
    if archetype.get("devhub_url"):
        lines.append(f"- **DevHub template:** {archetype['devhub_url']}")
    lines.append("")
    lines.append("## Goal")
    lines.append(f"- **Use case:** {intake.get('primary_use_case_description', '')}")
    if intake.get("user_stories"):
        lines.append("- **User stories:**")
        for story in intake["user_stories"]:
            lines.append(f"  - {story}")
    lines.append("")
    lines.append("## Workspace defaults")
    lines.append(f"- **Gold tables:** {', '.join(gold_tables) or '(none)'}")
    lines.append(f"- **Catalog.schema:** {', '.join(schemas) or '(none)'}")
    lines.append(f"- **Genie spaces:** {', '.join(genie_spaces) or '(none)'}")
    lines.append(
        f"- **Serving endpoints:** codegen=`{serving.get('codegen', 'n/a')}`, "
        f"planner=`{serving.get('planner', 'n/a')}`"
    )
    lines.append("")
    lines.append("## Auth (user authorization / OBO)")
    lines.append(
        "- Read the forwarded user token and build a per-request client; never "
        "print or log tokens."
    )
    lines.append(f"- **OBO header:** `{dbx.get('obo_header', 'x-forwarded-access-token')}`")
    lines.append(f"- **Required OAuth scopes:** {', '.join(scopes) or '(none)'}")
    lines.append(f"- **System env (read, never hardcode):** {', '.join(system_env) or '(none)'}")
    lines.append(
        "- Inside Databricks Apps, pin `auth_type='pat'` when building the "
        "WorkspaceClient from the forwarded token so the SDK does not also pick "
        "up the app service principal's OAuth env vars."
    )
    lines.append("")
    lines.append(design_system_markdown(target))
    lines.append("## Rules")
    lines.append("- Never assume a resource exists; honor the resource plan and approvals.")
    lines.append("- Implement only files marked `to_generate` in `app.manifest.yaml`.")
    lines.append("- Tag all created resources for governance.")
    lines.append("")
    return "\n".join(lines)
