"""Validation helpers for blueprints."""

from __future__ import annotations

from composer.models.blueprint import AppBlueprint


def validate_blueprint(blueprint: AppBlueprint) -> None:
    if not blueprint.pages:
        raise ValueError("Blueprint must include at least one page")
    if not blueprint.stories_traceability:
        raise ValueError("Blueprint must keep stories traceability")
