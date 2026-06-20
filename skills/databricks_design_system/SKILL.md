# Skill: databricks_design_system

Function: app_builder

## When to use

When generating UI for any archetype, apply a consistent Databricks look unless
the user specified their own design.

## How it works

`src/composer/codegen/design_system.py`:

- `PALETTE` - Databricks brand colors (`#FF3621`, `#0B2026`, `#EEEDE9`, `#F9F7F4`).
- `DESIGN_PRINCIPLES` - clean hierarchy, modern minimal, shadcn/Tailwind (AppKit)
  or CSS tokens (Python).
- `css_tokens()` - palette as CSS custom properties for the Python target.
- `design_system_markdown(target)` - a markdown block embedded in AGENTS.md.

## Rules

- AppKit target -> shadcn/ui on Tailwind; map palette to the Tailwind theme.
- Python target -> inject the CSS custom properties and style against them.
- Respect any user-specified design preference over these defaults.
- Reuse the existing `design_tokens` skill / `ux_ui_design__design_system` agent.
