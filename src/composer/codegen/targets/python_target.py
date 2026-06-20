"""Python (FastAPI/Streamlit) target plan for an archetype.

Returns the target-specific page list and extra files (e.g. the design-system
CSS tokens) the Python cascaron should include. The deterministic cascaron
emitter still produces the stubs; this module parameterizes them per archetype.
"""

from __future__ import annotations

from composer.archetypes.catalog import Archetype
from composer.codegen.design_system import css_tokens
from composer.models.intake import IntakeSpec

TARGET = "python"


def build_python_target(
    archetype: Archetype, intake: IntakeSpec, *, has_genie: bool = False
) -> dict:
    pages = list(archetype.ui_pages) or ["home"]
    extra_files: dict[str, str] = {"app/styles.css": css_tokens()}
    needs = set(archetype.required_primitives) | set(archetype.optional_primitives)
    return {
        "target": TARGET,
        "stack": "streamlit-python",
        "pages": pages,
        "extra_files": extra_files,
        "needs_genie": has_genie or "genie" in needs,
        "needs_lakebase": "lakebase" in needs,
        "needs_serving": "serving_endpoint" in needs,
    }
