"""Approval gates for write actions with dry-run support."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


# Per-resource decisions the user can take in the create-vs-reuse gate.
VALID_DECISIONS = ("create", "reuse", "skip")


class ApprovalGate:
    def __init__(self, root: str = ".appgen", dry_run: bool = True) -> None:
        self.approvals_dir = Path(root) / "approvals"
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = dry_run
        # resource_id -> decision ("create" | "reuse" | "skip")
        self._decisions: dict[str, str] = {}

    # -- per-resource create-vs-reuse gate -------------------------------
    def set_decision(self, resource_id: str, decision: str) -> None:
        """Record the user's create/reuse/skip decision for one resource."""
        if decision not in VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision '{decision}'. Expected one of {VALID_DECISIONS}."
            )
        self._decisions[resource_id] = decision

    def decision_for(self, resource_id: str, default: str = "create") -> str:
        """Return the decision for a resource, falling back to its default."""
        return self._decisions.get(resource_id, default)

    def apply_decisions(self, to_create: list[dict]) -> list[dict]:
        """Annotate a POST plan with the effective per-resource decision.

        Items decided ``skip`` are filtered out; the rest carry their effective
        ``decision`` so downstream provisioning only acts on approved resources.
        """
        result: list[dict] = []
        for item in to_create:
            rid = item.get("resource_id") or (
                f"{item.get('resource_type')}:{item.get('name')}"
            )
            decision = self.decision_for(rid, item.get("decision", "create"))
            if decision == "skip":
                continue
            enriched = dict(item)
            enriched["decision"] = decision
            result.append(enriched)
        return result

    def record(self, action: str, approved: bool, reason: str | None = None) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.approvals_dir / f"{ts}-{action}.yaml"
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "action": action,
                    "approved": approved,
                    "dry_run": self.dry_run,
                    "reason": reason,
                },
                f,
                sort_keys=False,
            )
        return path

    def ensure_allowed(self, action: str, approved: bool) -> None:
        if not approved:
            self.record(action=action, approved=False, reason="user denied")
            raise PermissionError(f"Action not approved: {action}")
        self.record(action=action, approved=True)
