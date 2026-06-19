"""Minimal orchestration graph representation."""

from __future__ import annotations

from composer.agent.state import AgentState


def run_graph(state: AgentState) -> AgentState:
    state.operation_log.extend(
        [
            "intake",
            "discovery",
            "metadata_audit",
            "metadata_enrichment_checkpoint",
            "genie_resolution",
            "blueprint_planning",
            "preflight",
            "deploy",
        ]
    )
    return state
