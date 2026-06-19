"""Pydantic schemas for intake and discovery artifacts."""

from __future__ import annotations

from pydantic import BaseModel


class StyleReferenceInput(BaseModel):
    source_type: str
    source_path_or_url: str
    style_guidelines_notes: str | None = None


class IntakeSpec(BaseModel):
    primary_use_case_description: str
    user_stories: list[str]
    gold_tables: list[str]
    existing_genies: list[str] = []
    workflow_requirements: str
    style_preferences: str
    access_requirements: str
    style_reference: StyleReferenceInput | None = None
