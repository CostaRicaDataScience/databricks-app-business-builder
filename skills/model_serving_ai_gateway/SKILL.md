# Skill: model_serving_ai_gateway

Function: app_builder

## When to use

Whenever the app (or the build-out) calls a foundation model / serving endpoint.

## How it works

`src/composer/llm/ai_gateway.py` `chat_completion(workspace_client, endpoint,
messages, request_tags=...)`:

- POSTs an OpenAI-compatible chat-completions request to
  `/serving-endpoints/{endpoint}/invocations` via the OBO `WorkspaceClient`.
- Attaches the `Databricks-Ai-Gateway-Request-Tags` header for governance.
- Returns the raw response (dict) or `None` on failure.

The Phase B build-out uses it for the planner (Opus) endpoint.

## Rules

- Always attach request tags (project + phase) for usage tracking.
- Run as the OBO user; never leak tokens.
- Degrade to the template fallback when the endpoint is unavailable.
- Reference: https://docs.databricks.com/aws/en/ai-gateway/query-endpoints-beta
