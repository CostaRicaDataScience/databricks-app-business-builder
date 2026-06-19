"""Databricks client abstraction and in-memory implementation."""

from __future__ import annotations

from dataclasses import dataclass

from modules.core.logging import log
from modules.domain.models import DiscoveryStatus
from modules.infra.auth import AuthContext


@dataclass(slots=True)
class TableMetadata:
    description: str | None
    columns: dict[str, str | None]


class DatabricksApiClient:
    """Simple client facade. Replace internals with real REST API calls."""

    def __init__(self, auth_context: AuthContext) -> None:
        self.auth_context = auth_context
        self._tables: dict[str, TableMetadata] = {
            "sales.gold_orders": TableMetadata(
                description="Orders fact table",
                columns={"order_id": "Primary key", "amount": "Order amount"},
            ),
            "sales.gold_customers": TableMetadata(
                description=None,
                columns={"customer_id": None, "segment": "Customer segment"},
            ),
        }
        self._genies: set[str] = {"sales_assistant"}

    def check_capability(self, capability: str) -> bool:
        if not self.auth_context.has_workspace_access:
            return False
        # In real implementation this maps to workspace entitlements/ACL checks.
        return capability in {
            "read_catalog",
            "manage_genie",
            "create_databricks_app",
            "tag_resources",
        }

    def get_table_metadata(self, table_name: str) -> TableMetadata | None:
        return self._tables.get(table_name)

    def table_status(self, table_name: str) -> DiscoveryStatus:
        metadata = self.get_table_metadata(table_name)
        if metadata is None:
            return DiscoveryStatus.MISSING
        missing_column_descriptions = any(v is None for v in metadata.columns.values())
        if metadata.description is None or missing_column_descriptions:
            return DiscoveryStatus.NEEDS_ENRICHMENT
        return DiscoveryStatus.EXISTS

    def enrich_table_metadata(
        self, table_name: str, table_description: str, column_descriptions: dict[str, str]
    ) -> None:
        metadata = self._tables.get(table_name)
        if metadata is None:
            metadata = TableMetadata(description=table_description, columns={})
            self._tables[table_name] = metadata
        metadata.description = table_description
        for column, description in column_descriptions.items():
            metadata.columns[column] = description
        log.info("table_metadata_enriched", table_name=table_name)

    def genie_exists(self, genie_name: str) -> bool:
        return genie_name in self._genies

    def create_genie(self, genie_name: str, use_case_description: str) -> None:
        # Placeholder for Genie best-practice creation workflow.
        self._genies.add(genie_name)
        log.info(
            "genie_created",
            genie_name=genie_name,
            use_case_description=use_case_description,
        )

    def create_databricks_app(self, app_name: str, output_path: str) -> list[str]:
        log.info("databricks_app_created", app_name=app_name, output_path=output_path)
        return [
            f"{output_path}/app.py",
            f"{output_path}/app.yaml",
            f"{output_path}/README.md",
        ]
