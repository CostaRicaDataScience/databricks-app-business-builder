"""AppKit (TypeScript) target via ``databricks apps init``.

DevHub's native stack. Requires Node + the Databricks CLI, so it is behind a
feature flag and degrades to a *plan* (no execution) when the toolchain is
missing or the flag is off. The ``runner`` injection makes it unit-testable.
"""

from __future__ import annotations

import shutil
from typing import Callable

from composer.archetypes.catalog import Archetype
from composer.core.logging import log
from composer.models.intake import IntakeSpec

TARGET = "appkit"

# Map our primitive vocabulary to AppKit plugin names.
_PRIMITIVE_TO_PLUGIN = {
    "lakebase": "lakebase",
    "genie": "genie",
    "serving_endpoint": "model-serving",
    "vector_search": "vector-search",
}


def appkit_available() -> bool:
    """True only when both the Databricks CLI and Node are on PATH."""
    return shutil.which("databricks") is not None and shutil.which("node") is not None


def plugins_for(archetype: Archetype) -> list[str]:
    needs = list(archetype.required_primitives) + list(archetype.optional_primitives)
    plugins: list[str] = []
    for primitive in needs:
        plugin = _PRIMITIVE_TO_PLUGIN.get(primitive)
        if plugin and plugin not in plugins:
            plugins.append(plugin)
    return plugins


def build_appkit_target(
    archetype: Archetype,
    intake: IntakeSpec,
    *,
    app_dir: str,
    enabled: bool = False,
    runner: Callable[[list[str]], object] | None = None,
) -> dict:
    """Return the AppKit plan and optionally execute ``databricks apps init``.

    When ``enabled`` is False or the toolchain is missing, returns a plan with
    ``executed=False`` and a ``reason`` - never raises.
    """
    plugins = plugins_for(archetype)
    command = ["databricks", "apps", "init", "--template", "appkit"]
    for plugin in plugins:
        command += ["--plugin", plugin]

    plan = {
        "target": TARGET,
        "stack": "appkit-typescript",
        "plugins": plugins,
        "pages": list(archetype.ui_pages),
        "command": command,
        "app_dir": app_dir,
        "executed": False,
        "reason": None,
    }

    if not enabled:
        plan["reason"] = "feature_flag_off"
        return plan
    if not appkit_available():
        plan["reason"] = "toolchain_missing (need databricks CLI + node)"
        return plan

    run = runner or _default_runner
    try:
        run(command)
        plan["executed"] = True
    except Exception as exc:  # pragma: no cover - depends on local toolchain
        log.error("appkit_init_failed", error=str(exc))
        plan["reason"] = f"init_failed: {exc}"
    return plan


def _default_runner(command: list[str]) -> object:  # pragma: no cover - real subprocess
    import subprocess

    return subprocess.run(command, check=True, capture_output=True, text=True)
