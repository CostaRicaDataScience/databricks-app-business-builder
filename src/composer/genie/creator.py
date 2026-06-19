"""Create Genie plans and execution payloads."""

from __future__ import annotations


def build_genie_creation_plan(genie_names: list[str], use_case: str) -> list[dict[str, object]]:
    return [
        {
            "genie_name": name,
            "use_case": use_case,
            "best_practice": "Keep scope focused and tables <= 5 when possible",
            "status": "planned",
        }
        for name in genie_names
    ]
