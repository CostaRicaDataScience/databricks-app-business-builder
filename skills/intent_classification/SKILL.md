# Skill: intent_classification

Function: app_builder

## When to use

Use this skill to turn a free-text intake into a concrete archetype + build
target before generating anything.

## How it works

`src/composer/archetypes/classifier.py` exposes `classify_intake(intake)` which
returns a `Classification`:

- `archetype_id`, `target` (`python`|`appkit`), `score`, `rationale`
- `candidates` — top scoring archetypes for transparency
- `needs_help` — True when confidence is below the floor; the UI should ask the
  user to confirm or choose.

## Rules

- Deterministic and offline-safe: keyword hits + primitive signals (e.g. a Genie
  reference boosts `genie_analytics`).
- Target is chosen from explicit hints in the intake (`appkit`/`typescript`/
  `react` vs `python`/`streamlit`), else the archetype default.
- An optional LLM client can refine the result when connected, but the
  rule-based result is always the floor.
