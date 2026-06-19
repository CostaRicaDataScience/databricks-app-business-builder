"""Domain contracts for the Databricks App business builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DiscoveryStatus(str, Enum):
    EXISTS = "exists"
    MISSING = "missing"
    NEEDS_ENRICHMENT = "needs_enrichment"
    NEEDS_CREATION = "needs_creation"
    # Honest status used when we could not verify the resource against a live
    # workspace (e.g. not connected). We never claim "exists" without checking.
    UNKNOWN = "unknown"


@dataclass(slots=True)
class StyleReferenceInput:
    source_type: str
    source_path_or_url: str
    style_guidelines_notes: str | None = None


@dataclass(slots=True)
class DiscoveryIntake:
    primary_use_case_description: str
    user_stories: list[str]
    gold_tables: list[str]
    existing_genies: list[str]
    workflow_requirements: str
    style_preferences: str
    access_requirements: str
    style_reference: StyleReferenceInput | None = None


@dataclass(slots=True)
class AppIntent:
    intake: DiscoveryIntake
    dry_run: bool = True
    run_provisioning: bool = False


@dataclass(slots=True)
class TableDiscovery:
    table_name: str
    status: DiscoveryStatus
    has_table_description: bool
    missing_columns: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GenieDiscovery:
    genie_name: str
    status: DiscoveryStatus
    reason: str | None = None


@dataclass(slots=True)
class DiscoveryReport:
    report_id: str
    tables: list[TableDiscovery]
    genies: list[GenieDiscovery]
    summary: str


@dataclass(slots=True)
class BuildPlan:
    plan_id: str
    summary: str
    implementation_steps: list[str]


@dataclass(slots=True)
class GeneratedArtifact:
    artifact_id: str
    output_path: str
    files_generated: list[str]
    # How the skeleton was produced: "llm" (real serving endpoint) or
    # "template" (deterministic offline fallback).
    source: str = "template"
    generator_endpoint: str | None = None
    preview: str | None = None


@dataclass(slots=True)
class TaggingReport:
    report_id: str
    required_tags: dict[str, str]
    resources_tagged: list[str]


@dataclass(slots=True)
class ProvisioningResult:
    operation_id: str
    actions_planned: list[str]
    actions_applied: list[str]
    rollback_hints: list[str]
    tagging_report: TaggingReport
