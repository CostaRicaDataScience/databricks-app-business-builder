"""Plan AppBlueprint from intake and discovery."""

from __future__ import annotations

import uuid

from composer.models.blueprint import AppBlueprint, DiscoveryReport
from composer.models.intake import IntakeSpec


def build_blueprint(intake: IntakeSpec, discovery: DiscoveryReport) -> AppBlueprint:
    pages = ["home", "insights", "genie_assistant"]
    trace: dict[str, list[str]] = {}
    for idx, story in enumerate(intake.user_stories):
        trace[f"story_{idx+1}"] = [story]
    style_tokens = {"theme": intake.style_preferences or "clean-modern"}
    return AppBlueprint(
        blueprint_id=str(uuid.uuid4()),
        pages=pages,
        stories_traceability=trace,
        style_tokens=style_tokens,
    )
