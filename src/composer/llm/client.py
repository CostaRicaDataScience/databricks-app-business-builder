"""Foundation Model client abstraction (Claude preferred with fallback)."""

from __future__ import annotations

import uuid

from composer.core.config import Settings
from composer.core.logging import log
from composer.models.blueprint import BuildPlan
from composer.models.intake import IntakeSpec


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_plan(self, intake: IntakeSpec) -> BuildPlan:
        # Placeholder deterministic implementation with provider metadata.
        plan_id = str(uuid.uuid4())
        summary = (
            f"Generated with endpoint={self.settings.foundation_model_endpoint} "
            f"preferred_model={self.settings.preferred_model}"
        )
        log.info("llm_plan_generated", plan_id=plan_id, endpoint=self.settings.foundation_model_endpoint)
        steps = [
            "Validate intake completeness and access requirements",
            "Discover gold tables and genie assets",
            "Fill metadata gaps with approval gates",
            "Generate AppBlueprint and Streamlit app",
            "Run preflight checks and deploy with tags",
        ]
        return BuildPlan(plan_id=plan_id, summary=summary, implementation_steps=steps)
