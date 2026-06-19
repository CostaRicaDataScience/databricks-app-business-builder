"""Pydantic schemas for planning, generation and governance artifacts."""

from __future__ import annotations

from pydantic import BaseModel


class BuildPlan(BaseModel):
    plan_id: str
    summary: str
    implementation_steps: list[str]


class AppBlueprint(BaseModel):
    blueprint_id: str
    pages: list[str]
    stories_traceability: dict[str, list[str]]
    style_tokens: dict[str, str]


class DiscoveryResourceStatus(BaseModel):
    name: str
    status: str
    details: str | None = None


class DiscoveryReport(BaseModel):
    report_id: str
    tables: list[DiscoveryResourceStatus]
    genies: list[DiscoveryResourceStatus]
    summary: str


class TaggingReport(BaseModel):
    report_id: str
    required_tags: dict[str, str]
    resources_tagged: list[str]


class ProvisioningResult(BaseModel):
    operation_id: str
    actions_planned: list[str]
    actions_applied: list[str]
    rollback_hints: list[str]
    tagging_report: TaggingReport
