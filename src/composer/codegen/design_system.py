"""Databricks design system defaults injected into generated apps.

DevHub's "Make it look great" guidance: shadcn/ui + Tailwind for AppKit, the
Databricks brand palette, clean hierarchy and modern spacing. For the Python
target we expose the same palette as CSS tokens so Streamlit/FastAPI apps share
the look.
"""

from __future__ import annotations

# Databricks brand palette (from DevHub).
PALETTE = {
    "primary": "#FF3621",   # Databricks red
    "ink": "#0B2026",       # near-black text / dark surfaces
    "surface": "#EEEDE9",   # light surface
    "background": "#F9F7F4",  # app background
}

DESIGN_PRINCIPLES = [
    "Clean hierarchy with modern spacing - avoid too many stacked cards.",
    "Modern, minimal design language.",
    "shadcn/ui on Tailwind for the AppKit target; equivalent CSS tokens for Python.",
    "Respect any user-specified design preference over these defaults.",
]


def css_tokens() -> str:
    """Return the palette as CSS custom properties (Python target)."""
    return (
        ":root {\n"
        f"  --dbx-primary: {PALETTE['primary']};\n"
        f"  --dbx-ink: {PALETTE['ink']};\n"
        f"  --dbx-surface: {PALETTE['surface']};\n"
        f"  --dbx-background: {PALETTE['background']};\n"
        "}\n"
    )


def design_system_markdown(target: str = "python") -> str:
    """Return a markdown block describing the design system for a target."""
    lines = ["## Design system (Databricks)", ""]
    lines.append("Palette:")
    for name, hex_value in PALETTE.items():
        lines.append(f"- `{name}`: `{hex_value}`")
    lines.append("")
    lines.append("Principles:")
    for principle in DESIGN_PRINCIPLES:
        lines.append(f"- {principle}")
    lines.append("")
    if target == "appkit":
        lines.append(
            "Use shadcn/ui components on Tailwind. Map the palette to your "
            "Tailwind theme (primary, ink, surface, background)."
        )
    else:
        lines.append(
            "For Streamlit/FastAPI, inject these CSS custom properties and style "
            "components against them:"
        )
        lines.append("")
        lines.append("```css")
        lines.append(css_tokens().rstrip())
        lines.append("```")
    lines.append("")
    return "\n".join(lines)
