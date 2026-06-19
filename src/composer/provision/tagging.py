"""Tagging governance helpers."""

from __future__ import annotations

import uuid

from composer.models.blueprint import TaggingReport


def enforce_tags(environment: str, owner: str, use_case_slug: str, resources: list[str]) -> TaggingReport:
    required_tags = {
        "project": "databricks-app-business-builder",
        "environment": environment,
        "owner": owner,
        "use_case": use_case_slug,
        "trace_id": str(uuid.uuid4()),
    }
    return TaggingReport(
        report_id=str(uuid.uuid4()),
        required_tags=required_tags,
        resources_tagged=resources,
    )
