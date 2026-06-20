"""Genie embedding plan + code snippet for generated apps.

Closes the "embed a Genie chat in the app" use case: plan which Genie spaces to
reuse vs create (delegating to the creator), and provide a Streamlit snippet the
build-out can drop into an embedded chat page.
"""

from __future__ import annotations

from composer.genie.creator import build_genie_creation_plan


def build_genie_embed_plan(
    genie_spaces: list[str], use_case: str, *, to_create: list[str] | None = None
) -> dict:
    """Return a plan: which spaces to reuse and which to create."""
    reuse = [g for g in genie_spaces if g]
    create = list(to_create or [])
    return {
        "reuse": reuse,
        "create": build_genie_creation_plan(create, use_case),
        "embed": bool(reuse or create),
    }


def genie_panel_snippet(space_id: str = "<GENIE_SPACE_ID>") -> str:
    """Return a Streamlit snippet to embed a Genie conversation panel (OBO)."""
    return (
        "import streamlit as st\n"
        "from databricks.sdk import WorkspaceClient\n\n"
        "def render_genie_panel(host: str, token: str | None, "
        f"space_id: str = '{space_id}') -> None:\n"
        "    # OBO: build a per-request client from the forwarded user token.\n"
        "    w = WorkspaceClient(host=host, token=token, auth_type='pat')\n"
        "    st.subheader('Pregunta a tus datos')\n"
        "    question = st.chat_input('Escribe tu pregunta...')\n"
        "    if question:\n"
        "        conv = w.genie.start_conversation_and_wait(space_id, question)\n"
        "        for attachment in getattr(conv, 'attachments', []) or []:\n"
        "            text = getattr(getattr(attachment, 'text', None), 'content', None)\n"
        "            if text:\n"
        "                st.write(text)\n"
    )
