"""Reuse-vs-create decisions for Genie assets."""

from __future__ import annotations

from composer.models.blueprint import DiscoveryReport


def genie_gap_report(discovery: DiscoveryReport) -> dict:
    needs_creation = [g.name for g in discovery.genies if g.status == "needs_creation"]
    reusable = [g.name for g in discovery.genies if g.status == "exists"]
    return {"reuse": reusable, "create": needs_creation}
