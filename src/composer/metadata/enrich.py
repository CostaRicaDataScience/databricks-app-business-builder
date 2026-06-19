"""Metadata enrichment proposal builder."""

from __future__ import annotations

from composer.models.blueprint import DiscoveryReport


def propose_metadata_updates(discovery: DiscoveryReport) -> list[dict[str, str]]:
    proposals: list[dict[str, str]] = []
    for table in discovery.tables:
        if table.status in {"missing", "needs_enrichment"}:
            proposals.append(
                {
                    "table": table.name,
                    "table_description": f"Business description for {table.name}",
                    "column_strategy": "autofill_missing_columns",
                }
            )
    return proposals
