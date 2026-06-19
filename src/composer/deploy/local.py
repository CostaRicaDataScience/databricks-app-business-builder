"""Local runtime helper for generated apps."""

from __future__ import annotations


def run_local(app_path: str) -> dict:
    return {"status": "ready", "hint": f"Run streamlit in {app_path}"}
