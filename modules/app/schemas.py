"""Pydantic schemas for API payloads."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StyleReferenceInputModel(BaseModel):
    source_type: str = Field(description="local_path or git_repo")
    source_path_or_url: str
    style_guidelines_notes: str | None = None


class DiscoveryIntakeRequest(BaseModel):
    primary_use_case_description: str
    user_stories: list[str]
    gold_tables: list[str]
    existing_genies: list[str] = []
    workflow_requirements: str
    style_preferences: str
    access_requirements: str
    style_reference: StyleReferenceInputModel | None = None


class RunPipelineRequest(BaseModel):
    """Full auto-run request. Same shape as the intake, but runs end-to-end."""

    primary_use_case_description: str
    user_stories: list[str]
    gold_tables: list[str]
    existing_genies: list[str] = []
    workflow_requirements: str
    style_preferences: str
    access_requirements: str
    style_reference: StyleReferenceInputModel | None = None


class DiscoveryRunRequest(BaseModel):
    intake_id: str


class DiscoveryConfirmRequest(BaseModel):
    intake_id: str
    report_id: str


class BuildPlanRequest(BaseModel):
    intake_id: str
    dry_run: bool = True
    run_provisioning: bool = False


class GenerateRequest(BaseModel):
    plan_id: str


class ProvisionRequest(BaseModel):
    intake_id: str
    environment: str
    owner: str
    use_case_slug: str
    resources: list[str]
