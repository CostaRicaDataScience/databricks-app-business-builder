"""AI Gateway query helper (OpenAI-compatible chat completions).

Standard route for invoking Databricks serving endpoints through the AI Gateway
with governance request-tags, running as the OBO user. See
https://docs.databricks.com/aws/en/ai-gateway/query-endpoints-beta
"""

from __future__ import annotations

import json

from composer.core.logging import log


def chat_completion(
    workspace_client: object,
    endpoint: str,
    messages: list[dict],
    *,
    request_tags: dict | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4000,
) -> object | None:
    """POST an OpenAI-compatible chat-completions request to ``endpoint``.

    Attaches the ``Databricks-Ai-Gateway-Request-Tags`` header for usage
    tracking. Returns the raw response (typically a dict), or ``None`` when the
    call fails so callers can degrade gracefully.
    """
    if workspace_client is None or not endpoint:
        return None
    body = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers: dict[str, str] = {}
    if request_tags:
        headers["Databricks-Ai-Gateway-Request-Tags"] = json.dumps(request_tags)
    try:
        api_client = workspace_client.api_client  # type: ignore[attr-defined]
        return api_client.do(
            "POST",
            f"/serving-endpoints/{endpoint}/invocations",
            body=body,
            headers=headers,
        )
    except Exception as exc:  # pragma: no cover - depends on live endpoint
        log.error("ai_gateway_query_failed", endpoint=endpoint, error=str(exc))
        return None
