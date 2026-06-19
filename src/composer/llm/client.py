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
from pathlib import Path

import yaml

from composer.core.logging import log
from composer.models.blueprint import AppBlueprint, BuildPlan, DiscoveryReport
from composer.models.intake import IntakeSpec

_SYSTEM_PROMPT = (
    "You are a senior Databricks engineer. Generate a minimal, runnable "
    "Streamlit Databricks App skeleton from the provided requirements. "
    "Respond with ONLY a JSON object mapping relative file paths to file "
    "contents (no prose, no markdown fences). Always include 'app.py'."
)

_BUILDOUT_SYSTEM_PROMPT = (
    "You are Claude Opus implementing a Databricks Streamlit App from a "
    "cascarón (scaffold). app.manifest.yaml is the source of truth and "
    "CONTRACTS.yaml lists the interfaces you must honor. Implement EXACTLY the "
    "single file you are asked for. The app uses user authorization (OBO): read "
    "x-forwarded-access-token from request headers and never print/log tokens. "
    "Respond with ONLY the raw file contents — no prose, no markdown fences."
)

# Default request tags attached to AI Gateway calls for usage tracking and
# governance. See https://docs.databricks.com/aws/en/ai-gateway/query-endpoints-beta
DEFAULT_REQUEST_TAGS = {
    "project": "databricks-app-business-builder",
    "phase": "build-out",
}


class LLMClient:
    def __init__(self, settings: object, workspace_client: object | None = None) -> None:
        self.settings = settings
        self.workspace_client = workspace_client

    @property
    def endpoint(self) -> str:
        return getattr(self.settings, "foundation_model_endpoint", "databricks-claude-sonnet")

    @property
    def planner_endpoint(self) -> str:
        """Separate Opus-class endpoint for the Phase B build-out."""
        return getattr(self.settings, "planner_model_endpoint", "databricks-claude-opus-4")

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

    # -- Phase B: build-out the cascarón via the planner endpoint ----------

    def build_out_cascaron(
        self,
        app_dir: str | Path,
        *,
        request_tags: dict | None = None,
    ) -> dict:
        """Fill the scaffold's ``to_generate`` files with Claude Opus.

        Reads ``app.manifest.yaml`` (source of truth), ``EXECUTION_PLAN.md`` and
        ``spec/`` from ``app_dir``, then for each file whose manifest
        ``status == 'to_generate'`` queries the planner endpoint (Claude Opus,
        via the Databricks AI Gateway, as the OBO user), writes the returned
        contents and flips the manifest status to ``generated``.

        Degrades gracefully: when no workspace client / planner endpoint is
        available (or the manifest is missing), nothing is written and every
        file stays ``to_generate`` — the scaffold remains valid and
        self-describing.
        """
        base = Path(app_dir)
        manifest_path = base / "app.manifest.yaml"
        result: dict = {
            "endpoint": self.planner_endpoint,
            "generated": [],
            "remaining": [],
            "phase": "not_started",
            "skipped": True,
            "reason": None,
        }
        if not manifest_path.exists():
            result["reason"] = "no_manifest"
            return result
        if self.workspace_client is None:
            result["reason"] = "no_workspace_client"
            result["remaining"] = self._manifest_to_generate(manifest_path)
            return result
        if not self.planner_endpoint:
            result["reason"] = "no_planner_endpoint"
            result["remaining"] = self._manifest_to_generate(manifest_path)
            return result

        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # pragma: no cover - corrupt manifest
            log.error("buildout_manifest_unreadable", error=str(exc))
            result["reason"] = "manifest_unreadable"
            return result

        plan_text = self._read_optional(base / "EXECUTION_PLAN.md")
        contracts_text = self._read_optional(base / "CONTRACTS.yaml")
        tags = request_tags or DEFAULT_REQUEST_TAGS

        files = manifest.get("files") or []
        result["skipped"] = False
        for entry in files:
            if not isinstance(entry, dict) or entry.get("status") != "to_generate":
                continue
            rel_path = entry.get("path")
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue
            prompt = self._build_buildout_prompt(
                entry, manifest, plan_text, contracts_text
            )
            content = self._query_planner(prompt, request_tags=tags)
            if not content:
                result["remaining"].append(rel_path)
                continue
            if not self._write_buildout_file(base, rel_path, content):
                result["remaining"].append(rel_path)
                continue
            entry["status"] = "generated"
            result["generated"].append(rel_path)

        result["phase"] = (
            "complete"
            if not result["remaining"]
            else ("partial" if result["generated"] else "not_started")
        )
        manifest.setdefault("build_out", {})["phase"] = result["phase"]
        try:
            manifest_path.write_text(
                yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover - best effort
            log.error("buildout_manifest_write_failed", error=str(exc))
        log.info(
            "llm_buildout_done",
            endpoint=self.planner_endpoint,
            generated=len(result["generated"]),
            remaining=len(result["remaining"]),
            phase=result["phase"],
        )
        return result

    @staticmethod
    def _manifest_to_generate(manifest_path: Path) -> list[str]:
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception:  # pragma: no cover - best effort
            return []
        return [
            e.get("path")
            for e in (manifest.get("files") or [])
            if isinstance(e, dict)
            and e.get("status") == "to_generate"
            and isinstance(e.get("path"), str)
        ]

    @staticmethod
    def _read_optional(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    @staticmethod
    def _write_buildout_file(base: Path, rel_path: str, content: str) -> bool:
        """Write a build-out file, refusing paths that escape ``base``."""
        target = (base / rel_path).resolve()
        base_resolved = base.resolve()
        if base_resolved != target and base_resolved not in target.parents:
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return True
        except Exception as exc:  # pragma: no cover - best effort
            log.error("buildout_write_failed", path=rel_path, error=str(exc))
            return False

    def _build_buildout_prompt(
        self,
        entry: dict,
        manifest: dict,
        plan_text: str,
        contracts_text: str,
    ) -> str:
        intake = manifest.get("intake", {})
        runtime = manifest.get("runtime", {})
        dbx = runtime.get("databricks_apps", {})
        return (
            f"Implement this single file of the Databricks App: {entry.get('path')}\n"
            f"Responsibility: {entry.get('purpose')}\n"
            f"Depends on: {', '.join(entry.get('depends_on') or []) or '(none)'}\n"
            f"Task id: {entry.get('produced_by_task')}\n\n"
            f"Use case: {intake.get('primary_use_case_description')}\n"
            f"Gold tables: {', '.join(intake.get('gold_tables') or []) or '(none)'}\n"
            f"Genie spaces: {', '.join(manifest.get('references', {}).get('genie_spaces') or []) or '(none)'}\n"
            f"Style: {intake.get('style_preferences')}\n\n"
            f"Runtime: stack={runtime.get('stack')}, "
            f"command={' '.join(runtime.get('command') or [])}\n"
            f"Auth: {dbx.get('authorization')} via header "
            f"{dbx.get('obo_header')}; OAuth scopes="
            f"{', '.join(dbx.get('required_oauth_scopes') or [])}\n"
            f"System env (read, do not hardcode): "
            f"{', '.join(dbx.get('system_env') or [])}\n\n"
            "Contracts to honor (CONTRACTS.yaml):\n"
            f"{contracts_text}\n"
            "Execution plan (EXECUTION_PLAN.md) excerpt for context follows; "
            "implement ONLY the file named above.\n"
            f"{plan_text[:4000]}\n"
        )

    def _query_planner(self, prompt: str, *, request_tags: dict | None = None) -> str | None:
        """Query the planner endpoint via the AI Gateway with request tags.

        Uses the OpenAI-compatible MLflow Chat Completions invocation and
        attaches the ``Databricks-Ai-Gateway-Request-Tags`` header for usage
        tracking / governance, running as the OBO user. See
        https://docs.databricks.com/aws/en/ai-gateway/query-endpoints-beta

        Returns the raw file contents, or ``None`` when the call fails or the
        response is not a parseable chat-completions object (so the caller can
        leave the file ``to_generate``).
        """
        body = {
            "messages": [
                {"role": "system", "content": _BUILDOUT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 4000,
        }
        headers = {}
        if request_tags:
            # Tags are passed as a JSON-encoded header value per the AI Gateway doc.
            headers["Databricks-Ai-Gateway-Request-Tags"] = json.dumps(request_tags)
        try:
            api_client = self.workspace_client.api_client  # type: ignore[attr-defined]
            response = api_client.do(
                "POST",
                f"/serving-endpoints/{self.planner_endpoint}/invocations",
                body=body,
                headers=headers,
            )
        except Exception as exc:  # pragma: no cover - depends on live endpoint
            log.error("llm_buildout_query_failed", error=str(exc))
            return None
        # Real AI Gateway responses are JSON objects; anything else (e.g. a mock
        # without a configured return) is treated as "no content" so we degrade.
        if not isinstance(response, dict):
            return None
        text = self._extract_text(response)
        cleaned = self._strip_fences(text)
        return cleaned or None

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
    def _strip_fences(content: str) -> str:
        """Strip leading/trailing markdown code fences from model output."""
        if not content:
            return ""
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9_.-]*\n", "", text)
            text = re.sub(r"\n```$", "", text)
        return text.strip()

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
