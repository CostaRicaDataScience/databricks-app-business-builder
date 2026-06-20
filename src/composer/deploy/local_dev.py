"""Local dev environment preflight (DevHub "Set Up Your Local Dev Environment").

Verifies the prerequisites every CLI/deploy step assumes:
- Databricks CLI installed and on PATH (>= 1.0)
- at least one authenticated profile (``databricks auth profiles`` -> Valid: YES)
- optional: ``databricks aitools version`` (agent skills)

``runner`` is injectable so this is unit-testable and never blocks; in a deployed
Databricks App there is no CLI, so callers should only use this for local dev.
"""

from __future__ import annotations

import shutil
from typing import Callable

# runner(cmd: list[str]) -> tuple[returncode, stdout]
Runner = Callable[[list[str]], "tuple[int, str]"]


def _default_runner(cmd: list[str]) -> tuple[int, str]:  # pragma: no cover - real subprocess
    import subprocess

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def _parse_profiles(stdout: str) -> list[dict]:
    """Parse ``databricks auth profiles`` table output into rows."""
    profiles: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name"):
            continue
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        valid = "YES" in line.upper()
        profiles.append({"name": name, "valid": valid})
    return profiles


def local_dev_preflight(runner: Runner | None = None) -> dict:
    """Return a structured preflight of the local Databricks dev environment."""
    cli_path = shutil.which("databricks")
    result = {
        "cli_installed": cli_path is not None,
        "cli_path": cli_path,
        "cli_version": None,
        "profiles": [],
        "has_valid_profile": False,
        "aitools_version": None,
        "ready": False,
    }
    if cli_path is None:
        return result
    run = runner or _default_runner

    rc, out = run(["databricks", "--version"])
    if rc == 0:
        result["cli_version"] = out.strip().splitlines()[0] if out.strip() else None

    rc, out = run(["databricks", "auth", "profiles"])
    if rc == 0:
        profiles = _parse_profiles(out)
        result["profiles"] = profiles
        result["has_valid_profile"] = any(p["valid"] for p in profiles)

    rc, out = run(["databricks", "aitools", "version"])
    if rc == 0 and out.strip():
        result["aitools_version"] = out.strip().splitlines()[0]

    result["ready"] = bool(result["cli_installed"] and result["has_valid_profile"])
    return result
