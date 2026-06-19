"""Foundation Model client.

Two responsibilities:

* :meth:`LLMClient.build_plan` — produce a short ``BuildPlan`` (implementation
  steps). This stays lightweight/deterministic.
* :meth:`LLMClient.generate_app_source` — generate the **actual app skeleton**
  (the bootstrap ``app.py`` and supporting files) by calling a real Databricks
  **serving endpoint** through the authenticated ``WorkspaceClient`` (OBO user
  token when present). The model output drives codegen.

When no workspace client / serving endpoint is available (local dev, tests,
headless), ``generate_app_source`` returns ``None`` and the caller uses the
deterministic template fallback — so the project always works offline.
"""

from __future__ import annotations

import json
import re
import uuid

from composer.core.logging import log
from composer.models.blueprint import AppBlueprint, BuildPlan, DiscoveryReport
from composer.models.intake import IntakeSpec

_SYSTEM_PROMPT = (
    "You are a senior Databricks engineer. Generate a minimal, runnable "
    "Streamlit Databricks App skeleton from the provided requirements. "
    "Respond with ONLY a JSON object mapping relative file paths to file "
    "contents (no prose, no markdown fences). Always include 'app.py'."
)


class LLMClient:
    def __init__(self, settings: object, workspace_client: object | None = None) -> None:
        self.settings = settings
        self.workspace_client = workspace_client

    @property
    def endpoint(self) -> str:
        return getattr(self.settings, "foundation_model_endpoint", "databricks-claude-sonnet")

    @property
    def preferred_model(self) -> str:
        return getattr(self.settings, "preferred_model", "claude")

    def build_plan(self, intake: IntakeSpec) -> BuildPlan:
        # Lightweight deterministic plan (steps), independent of the endpoint.
        plan_id = str(uuid.uuid4())
        summary = (
            f"Generated with endpoint={self.endpoint} "
            f"preferred_model={self.preferred_model}"
        )
        log.info("llm_plan_generated", plan_id=plan_id, endpoint=self.endpoint)
        steps = [
            "Validate intake completeness and access requirements",
            "Discover gold tables and genie assets",
            "Fill metadata gaps with approval gates",
            "Generate AppBlueprint and Streamlit app",
            "Run preflight checks and deploy with tags",
        ]
        return BuildPlan(plan_id=plan_id, summary=summary, implementation_steps=steps)

    def generate_app_source(
        self,
        intake: IntakeSpec,
        blueprint: AppBlueprint,
        discovery: DiscoveryReport | None = None,
        inventory: dict | None = None,
    ) -> dict[str, str] | None:
        """Generate app source files via the serving endpoint, or None to fall back.

        Runs as the authenticated user (the ``workspace_client`` is built from
        the OBO/user token), so generation uses the same workspace that was
        authenticated for the request. ``inventory`` carries the GET results of
        existing workspace resources and the POST plan so the generated skeleton
        wires up real resources and stubs the ones that must be created.
        """
        if self.workspace_client is None:
            log.info("llm_codegen_fallback", reason="no_workspace_client")
            return None
        try:
            prompt = self._build_codegen_prompt(intake, blueprint, discovery, inventory)
            content = self._query_endpoint(prompt)
            files = self._parse_files(content)
            if not files:
                log.info("llm_codegen_fallback", reason="empty_or_unparseable")
                return None
            log.info(
                "llm_codegen_generated",
                endpoint=self.endpoint,
                files=len(files),
            )
            return files
        except Exception as exc:  # pragma: no cover - depends on live endpoint
            log.error("llm_codegen_failed", error=str(exc))
            return None

    # -- internals --------------------------------------------------------

    def _build_codegen_prompt(
        self,
        intake: IntakeSpec,
        blueprint: AppBlueprint,
        discovery: DiscoveryReport | None,
        inventory: dict | None = None,
    ) -> str:
        tables = ", ".join(intake.gold_tables) or "(none specified)"
        stories = "; ".join(intake.user_stories) or "(none specified)"
        pages = ", ".join(blueprint.pages)
        discovered = ""
        if discovery is not None:
            discovered = "; ".join(
                f"{t.name}={t.status}" for t in discovery.tables
            )
        resources_block = self._inventory_text(inventory)
        return (
            "Build a Streamlit Databricks App with these requirements.\n"
            f"Use case: {intake.primary_use_case_description}\n"
            f"User stories: {stories}\n"
            f"Gold tables: {tables}\n"
            f"Discovered tables: {discovered or '(n/a)'}\n"
            f"Pages: {pages}\n"
            f"Style preferences: {intake.style_preferences}\n"
            f"Access requirements: {intake.access_requirements}\n"
            f"{resources_block}"
            "Wire the app to the EXISTING resources listed above (serving "
            "endpoints, Genie spaces, tables, volumes). For resources under "
            "'To create', add clearly-marked TODO stubs instead of assuming they "
            "exist.\n"
            "Return a JSON object: {\"app.py\": \"...\", \"app.yaml\": \"...\", "
            "\"README.md\": \"...\"}."
        )

    @staticmethod
    def _inventory_text(inventory: dict | None) -> str:
        if not inventory:
            return ""
        lines = ["Workspace resources (from live GET calls):"]
        for key, info in (inventory.get("resources") or {}).items():
            existing = ", ".join(info.get("existing") or []) or "(none/unchecked)"
            lines.append(f"- {key}: {existing}")
        to_create = inventory.get("to_create") or []
        if to_create:
            lines.append("To create (POST):")
            for item in to_create:
                lines.append(
                    f"- {item.get('resource_type')}: {item.get('name')} "
                    f"({item.get('reason')})"
                )
        return "\n".join(lines) + "\n"

    def _query_endpoint(self, prompt: str) -> str:
        """Query the Databricks serving endpoint (OpenAI-compatible messages)."""
        try:
            from databricks.sdk.service.serving import (  # type: ignore
                ChatMessage,
                ChatMessageRole,
            )

            messages = [
                ChatMessage(role=ChatMessageRole.SYSTEM, content=_SYSTEM_PROMPT),
                ChatMessage(role=ChatMessageRole.USER, content=prompt),
            ]
        except Exception:  # pragma: no cover - SDK shape fallback
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

        response = self.workspace_client.serving_endpoints.query(  # type: ignore[attr-defined]
            name=self.endpoint,
            messages=messages,
            temperature=0.1,
            max_tokens=4000,
        )
        return self._extract_text(response)

    @staticmethod
    def _extract_text(response: object) -> str:
        """Pull the assistant message text out of a serving-endpoint response."""
        choices = getattr(response, "choices", None)
        if choices:
            first = choices[0]
            message = getattr(first, "message", None)
            if message is not None:
                content = getattr(message, "content", None)
                if content:
                    return content
            text = getattr(first, "text", None)
            if text:
                return text
        # Dict-shaped fallbacks.
        if isinstance(response, dict):
            ch = response.get("choices") or []
            if ch:
                msg = ch[0].get("message") or {}
                if msg.get("content"):
                    return msg["content"]
        return str(response)

    @staticmethod
    def _parse_files(content: str) -> dict[str, str]:
        """Parse a JSON object of ``{path: contents}`` from the model output."""
        if not content:
            return {}
        text = content.strip()
        # Strip code fences if the model added them despite instructions.
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9]*\n", "", text)
            text = re.sub(r"\n```$", "", text)
        try:
            data = json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}
            try:
                data = json.loads(match.group(0))
            except Exception:
                return {}
        if not isinstance(data, dict):
            return {}
        files: dict[str, str] = {}
        for path, body in data.items():
            if isinstance(path, str) and isinstance(body, str) and path.strip():
                files[path] = body
        return files
