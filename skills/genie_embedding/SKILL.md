# Skill: genie_embedding

Function: app_builder

## When to use

For archetypes that embed AI/BI Genie conversational analytics (genie_analytics,
or any app where users should chat with their data).

## How it works

- `src/composer/genie/embed.py`:
  - `build_genie_embed_plan(genie_spaces, use_case, to_create=...)` - plan which
    spaces to reuse vs create (delegates to `genie/creator.build_genie_creation_plan`).
  - `genie_panel_snippet(space_id)` - a Streamlit snippet that builds an OBO
    WorkspaceClient and renders a Genie conversation panel.

## Rules

- Prefer reusing an existing Genie space; create only with explicit approval.
- Use OBO (`auth_type='pat'`); never log tokens.
- Declare the Genie space as an app resource in `app.yaml`.
