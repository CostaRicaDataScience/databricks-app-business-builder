"""Archetype catalog + classifier.

DevHub publishes a curated set of *archetypes* (cookbooks/recipes) that describe
*what* to build on the Databricks developer stack. This package mirrors that
idea: a small registry of supported archetypes plus a classifier that maps a
free-text intake to the best-fit archetype and a build target (python|appkit).
"""

from composer.archetypes.catalog import (
    Archetype,
    ARCHETYPES,
    default_archetype,
    get_archetype,
    list_archetypes,
)
from composer.archetypes.classifier import Classification, classify_intake

__all__ = [
    "Archetype",
    "ARCHETYPES",
    "Classification",
    "classify_intake",
    "default_archetype",
    "get_archetype",
    "list_archetypes",
]
