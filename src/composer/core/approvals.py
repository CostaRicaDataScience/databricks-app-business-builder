"""Approval gates for write actions with dry-run support."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


class ApprovalGate:
    def __init__(self, root: str = ".appgen", dry_run: bool = True) -> None:
        self.approvals_dir = Path(root) / "approvals"
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = dry_run

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
