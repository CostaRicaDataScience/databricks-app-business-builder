"""Shared state model for orchestration graph."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentState:
    intake_id: str | None = None
    discovery_report_id: str | None = None
    blueprint_id: str | None = None
    operation_log: list[str] = field(default_factory=list)
