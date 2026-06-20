"""Lakebase (managed Postgres) provisioning plan + gated execution.

Provisioning costs money and takes minutes, so creation is always behind an
explicit approval and supports dry-run. Discovery/reuse is handled by the
inventory (Phase 2); this module plans and (when approved) creates.
"""

from __future__ import annotations

from composer.core.logging import log

# Default schema/tables for chat-history archetypes (ai_chat / rag_chat).
DEFAULT_CHAT_SCHEMA = "chat"
DEFAULT_CHAT_TABLES = ("chats", "messages")


def plan_lakebase_steps(instance_name: str, *, with_chat_memory: bool = False) -> list[str]:
    steps = [
        f"Create Lakebase instance '{instance_name}' (managed Postgres).",
        "Create a production branch + endpoint and capture connection values.",
    ]
    if with_chat_memory:
        steps.append(
            f"Create schema '{DEFAULT_CHAT_SCHEMA}' with tables "
            f"{', '.join(DEFAULT_CHAT_TABLES)} for agent memory."
        )
    return steps


def provision_lakebase(
    client: object | None,
    instance_name: str,
    *,
    approved: bool,
    dry_run: bool = True,
    with_chat_memory: bool = False,
) -> dict:
    """Plan (and, if approved + not dry-run, create) a Lakebase instance.

    Returns a result dict; never raises on a missing client/SDK.
    """
    steps = plan_lakebase_steps(instance_name, with_chat_memory=with_chat_memory)
    result = {
        "instance": instance_name,
        "steps": steps,
        "approved": approved,
        "dry_run": dry_run,
        "status": "planned",
    }
    if not approved:
        result["status"] = "blocked_needs_approval"
        return result
    if dry_run:
        result["status"] = "planned"  # approved but simulated
        return result
    if client is None or not getattr(client, "has_real_client", lambda: False)():
        result["status"] = "skipped_no_client"
        return result
    # Real creation is workspace-dependent; we record intent and let the caller's
    # SDK wiring perform the create. We keep this defensive and side-effect-free
    # in tests by requiring an explicit create method on the client.
    creator = getattr(client, "create_lakebase_instance", None)
    if not callable(creator):
        result["status"] = "skipped_unsupported_sdk"
        return result
    try:
        creator(name=instance_name)  # pragma: no cover - depends on live workspace
        result["status"] = "created"
    except Exception as exc:  # pragma: no cover - depends on live workspace
        log.error("lakebase_create_failed", name=instance_name, error=str(exc))
        result["status"] = f"failed: {exc}"
    return result
