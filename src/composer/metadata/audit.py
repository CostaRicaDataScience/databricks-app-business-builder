"""Metadata quality audit."""

from __future__ import annotations

from composer.models.blueprint import DiscoveryReport


def build_metadata_quality_report(discovery: DiscoveryReport) -> dict:
    missing = [t.name for t in discovery.tables if t.status in {"missing", "needs_enrichment"}]
    return {
        "tables_missing_metadata": missing,
        "table_count": len(discovery.tables),
    }
