"""Tagging policy enforcement for compute/jobs/pipelines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TaggingPolicy:
    required_keys: tuple[str, ...] = (
        "project",
        "environment",
        "owner",
        "use_case",
        "trace_id",
    )

    def validate(self, tags: dict[str, str]) -> None:
        missing = [k for k in self.required_keys if not tags.get(k)]
        if missing:
            missing_csv = ",".join(missing)
            raise ValueError(f"Missing required tagging keys: {missing_csv}")
