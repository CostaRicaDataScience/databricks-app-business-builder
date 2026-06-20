"""Build targets for the generated app.

Two targets, selected per archetype:
- ``python``  - FastAPI/Streamlit (default; matches the deployed builder).
- ``appkit``  - DevHub AppKit/TypeScript scaffold via ``databricks apps init``.
"""

from composer.codegen.targets.appkit_target import (
    appkit_available,
    build_appkit_target,
)
from composer.codegen.targets.python_target import build_python_target

__all__ = ["appkit_available", "build_appkit_target", "build_python_target"]
