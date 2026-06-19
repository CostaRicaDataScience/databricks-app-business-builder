"""Reuse-vs-create decisions for Genie assets.

The heuristic (a name containing ``new`` implies it must be created) is the
default and keeps the project usable with no workspace access. When MCP is
active, :func:`resolve_genie_status` consults the real Genie spaces reported by
the Databricks MCP server before deciding, falling back to the heuristic when
MCP is inconclusive.
"""

from __future__ import annotations

from collections.abc import Sequence

from composer.models.blueprint import DiscoveryReport

# Phrases that indicate the user is asking us to SEARCH for a Genie rather than
# naming an existing one (e.g. "no estoy seguro, quiero que busques").
_SEARCH_INTENT_PHRASES = (
    "busca",
    "buscar",
    "busque",
    "busques",
    "no estoy seguro",
    "no se",
    "no sé",
    "encuentra",
    "encontrar",
    "averigua",
    "revisa",
    "search",
    "not sure",
    "find one",
)


def is_search_request(text: str) -> bool:
    """True when the free-text Genie field is a request to search, not a name.

    A real Genie name is short and identifier-like. Sentences, questions, or
    phrases like "no estoy seguro, quiero que busques" are treated as a request
    to search the workspace instead of as a literal Genie name.
    """
    value = (text or "").strip().lower()
    if not value:
        return False
    if any(phrase in value for phrase in _SEARCH_INTENT_PHRASES):
        return True
    if "?" in value or "," in value:
        return True
    # Long, sentence-like input is not a Genie identifier.
    return len(value.split()) > 4


def _matches_existing(genie: str, genie_spaces: Sequence[str]) -> bool:
    needle = genie.strip().lower()
    return any(needle == space.strip().lower() for space in genie_spaces)


def resolve_genie_status(
    genie: str,
    genie_spaces: Sequence[str] | None = None,
    mcp_active: bool = False,
) -> tuple[str, str | None]:
    """Decide whether a requested Genie exists or needs creation.

    Returns ``(status, details)`` where status is ``"exists"`` or
    ``"needs_creation"``.
    """
    genie_spaces = genie_spaces or []
    if mcp_active and genie_spaces:
        if _matches_existing(genie, genie_spaces):
            return "exists", "Confirmed against Genie spaces via MCP"
        return "needs_creation", "Not present in Genie spaces reported by MCP"

    # Heuristic fallback (no MCP / no reported spaces).
    if "new" in genie:
        return "needs_creation", "Requested genie does not exist"
    return "exists", None


def genie_gap_report(discovery: DiscoveryReport) -> dict:
    needs_creation = [g.name for g in discovery.genies if g.status == "needs_creation"]
    reusable = [g.name for g in discovery.genies if g.status == "exists"]
    return {"reuse": reusable, "create": needs_creation}
