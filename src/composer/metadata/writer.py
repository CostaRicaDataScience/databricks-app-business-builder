"""Apply approved metadata updates."""

from __future__ import annotations


def apply_metadata_updates(proposals: list[dict[str, str]], approved: bool, dry_run: bool) -> dict:
    if not approved:
        return {"applied": [], "skipped": [p["table"] for p in proposals], "reason": "not approved"}
    if dry_run:
        return {"applied": [], "planned": [p["table"] for p in proposals], "dry_run": True}
    return {"applied": [p["table"] for p in proposals], "dry_run": False}
