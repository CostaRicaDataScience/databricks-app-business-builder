# MCP integration (Databricks Model Context Protocol)

This project can optionally talk to a **Databricks MCP server** to verify Unity
Catalog tables/metadata during discovery and to check real Genie spaces during
reuse-vs-create decisions. MCP is **disabled by default** — with no
`MCP_SERVER_URL` set, the project keeps using its existing heuristic discovery
and the behavior is unchanged.

## Upstream awareness

- **Upstream repo:** [`databrickslabs/mcp`](https://mcpservers.org/servers/databrickslabs/mcp).
  The Unity Catalog labs server exposes UC functions, Vector Search, and Genie
  spaces as MCP tools.
- **Recommendation:** Databricks now recommends **Managed MCP servers**, and the
  labs Unity Catalog server is **deprecated**. Prefer Managed MCP. Only fall
  back to the labs server if you have a specific need, and pin the dependency.
- We **do not vendor** the upstream repo. We depend on the standard `mcp` Python
  package (the protocol client) and talk to whatever server URL is configured.

### How to stay aligned with upstream

1. **Prefer Managed MCP.** Each Databricks App exposes a Managed MCP endpoint at:

   ```
   https://<app-url>.databricksapps.com/api/mcp/
   ```

   Note the **required trailing `/api/mcp/`**. Point `MCP_SERVER_URL` at it.
2. **Pin the client dependency** (`mcp>=1.2` in `pyproject.toml`). Bump
   deliberately and re-run the test suite when upgrading.
3. **Watch the deprecation.** If you currently use the labs UC server, plan a
   migration to Managed MCP; the tool surface (UC functions, Vector Search,
   Genie) is equivalent.
4. **No hardcoded tool names.** `MCPClient` discovers tools via `list_tools()`
   so it tolerates upstream tool renames; higher-level helpers degrade to the
   heuristic if the server shape changes.

## Transport & auth

- **Transport:** Streamable HTTP (`mcp.client.streamable_http`).
- **Auth:** `Authorization: Bearer <token>`, where the token is the **per-request
  OBO user token** when the app runs inside Databricks Apps (see
  [`README` → Databricks Apps OBO](../../README.md)), or the configured fallback
  token otherwise. This means MCP calls run with the signed-in user's real
  permissions.

## Configuration

| Env var               | Setting               | Purpose                                          |
| --------------------- | --------------------- | ------------------------------------------------ |
| `MCP_SERVER_URL`      | `mcp_server_url`      | MCP endpoint (`.../api/mcp/`). Empty = disabled. |
| `MCP_GENIE_SPACE_IDS` | `mcp_genie_space_ids` | Comma-separated Genie space ids to consider.     |
| `MCP_UC_SCHEMA`       | `mcp_uc_schema`       | Optional UC schema scope for table checks.       |

## Where it is wired

- `src/composer/mcp/client.py` — the configurable `MCPClient` (`list_tools`,
  `call_tool`, `verify_uc_table`, `list_genie_spaces`). Degrades gracefully if
  the `mcp` package or the server is unavailable (never crashes).
- `src/composer/discovery/service.py` — when MCP is available, table statuses
  are annotated with MCP verification; otherwise heuristic only.
- `src/composer/genie/resolver.py` — when MCP is available, reuse-vs-create is
  decided against real Genie spaces; otherwise the name heuristic is used.

## Graceful degradation

Every MCP path is best-effort. If the package is missing, the URL is unset, or
the server is unreachable, helpers return safe empty/`None` results and the
caller keeps its existing heuristic. The app never fails because MCP is down.
