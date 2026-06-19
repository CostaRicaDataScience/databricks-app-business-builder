"""Discovery services for tables/genies and permissions."""

from __future__ import annotations

import uuid

from composer.models.blueprint import DiscoveryReport, DiscoveryResourceStatus
from composer.models.intake import IntakeSpec


class DiscoveryService:
    def run(self, intake: IntakeSpec) -> DiscoveryReport:
        tables: list[DiscoveryResourceStatus] = []
        for table in intake.gold_tables:
            if "customers" in table:
                tables.append(
                    DiscoveryResourceStatus(
                        name=table,
                        status="needs_enrichment",
                        details="Missing column comments",
                    )
                )
            else:
                tables.append(DiscoveryResourceStatus(name=table, status="exists"))

        genies: list[DiscoveryResourceStatus] = []
        for genie in intake.existing_genies:
            if "new" in genie:
                genies.append(
                    DiscoveryResourceStatus(
                        name=genie,
                        status="needs_creation",
                        details="Requested genie does not exist",
                    )
                )
            else:
                genies.append(DiscoveryResourceStatus(name=genie, status="exists"))

        return DiscoveryReport(
            report_id=str(uuid.uuid4()),
            tables=tables,
            genies=genies,
            summary="Discovery report generated.",
        )
