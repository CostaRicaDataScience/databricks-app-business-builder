"""Tests for the configurable MCP client and its discovery/genie integration.

Verifies: disabled-by-default behavior (no URL -> not available, heuristic
path), and that when configured the discovery/genie paths call the MCP client.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from composer.core.config import Settings
from composer.discovery.service import DiscoveryService
from composer.genie.resolver import resolve_genie_status
from composer.mcp.client import MCPClient
from composer.models.intake import IntakeSpec


def _settings(**overrides) -> Settings:
    base = dict(
        databricks_host="https://x",
        databricks_token="tok",
        databricks_profile=None,
        auth_mode="user_workspace",
        sp_client_id=None,
        sp_client_secret=None,
        foundation_model_endpoint="databricks-claude-sonnet",
        preferred_model="claude",
        fallback_model="fallback",
        appgen_dir=".appgen",
        output_root="./generated_apps",
        dry_run_default=True,
    )
    base.update(overrides)
    return Settings(**base)


def _intake() -> IntakeSpec:
    return IntakeSpec(
        primary_use_case_description="Sales app",
        user_stories=["As analyst I want KPIs"],
        gold_tables=["sales.gold_orders", "sales.gold_customers"],
        existing_genies=["sales_assistant", "new_sales_genie"],
        workflow_requirements="daily",
        style_preferences="clean",
        access_requirements="read",
    )


def test_mcp_disabled_by_default():
    settings = _settings()  # no mcp_server_url
    mcp = MCPClient.from_settings(settings, token="tok")
    assert mcp.is_configured() is False
    assert mcp.is_available() is False
    # Helpers degrade safely with no network calls.
    assert mcp.list_tools() == []
    assert mcp.verify_uc_table("sales.gold_orders") is None
    assert mcp.list_genie_spaces() == []


def test_mcp_configured_but_helpers_degrade_when_unreachable():
    settings = _settings(mcp_server_url="https://app.databricksapps.com/api/mcp/")
    mcp = MCPClient.from_settings(settings, token="tok")
    assert mcp.is_configured() is True
    # is_available() is True (configured + sdk present), but actual network
    # calls fail and degrade to safe defaults rather than raising.
    assert mcp.list_tools() == []
    assert mcp.verify_uc_table("sales.gold_orders") is None


def test_discovery_reports_unknown_without_workspace_or_mcp():
    # Honest behavior: with no workspace connection and no MCP, we never claim a
    # table "exists" — it is reported as unknown until verified.
    report = DiscoveryService(mcp_client=None, workspace=None).run(_intake())
    statuses = {t.name: t.status for t in report.tables}
    assert statuses["sales.gold_orders"] == "unknown"
    assert statuses["sales.gold_customers"] == "unknown"
    genie_statuses = {g.name: g.status for g in report.genies}
    assert genie_statuses["sales_assistant"] == "exists"
    assert genie_statuses["new_sales_genie"] == "needs_creation"
    assert "MCP" not in report.summary


def test_discovery_calls_mcp_client_when_configured():
    mock_mcp = MagicMock()
    mock_mcp.is_available.return_value = True
    mock_mcp.verify_uc_table.return_value = True
    mock_mcp.list_genie_spaces.return_value = ["sales_assistant"]

    report = DiscoveryService(mcp_client=mock_mcp).run(_intake())

    # Discovery consulted MCP for each table and for genie spaces.
    assert mock_mcp.verify_uc_table.call_count == 2
    mock_mcp.list_genie_spaces.assert_called_once()
    assert "MCP" in report.summary
    # MCP-confirmed genie marked as existing; the other needs creation.
    genie_statuses = {g.name: g.status for g in report.genies}
    assert genie_statuses["sales_assistant"] == "exists"
    assert genie_statuses["new_sales_genie"] == "needs_creation"
    # Table detail annotated with MCP verification.
    orders = next(t for t in report.tables if t.name == "sales.gold_orders")
    assert "MCP" in (orders.details or "")


def test_resolve_genie_status_prefers_mcp_spaces():
    status, details = resolve_genie_status(
        "marketing_genie",
        genie_spaces=["marketing_genie", "sales_assistant"],
        mcp_active=True,
    )
    assert status == "exists"
    assert "MCP" in (details or "")

    status, details = resolve_genie_status(
        "unknown_space", genie_spaces=["sales_assistant"], mcp_active=True
    )
    assert status == "needs_creation"
