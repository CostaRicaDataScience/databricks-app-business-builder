"""Per-request on-behalf-of-user (OBO) authentication for Databricks Apps.

When this app runs inside Databricks Apps with *user authorization* enabled,
the platform forwards the end user's identity and a short-lived OAuth access
token on every request via HTTP headers:

* ``X-Forwarded-Access-Token`` — the user's OAuth access token (used for OBO).
* ``X-Forwarded-Email`` / ``X-Forwarded-User`` — the user's identity.

We use these to build a **per-request** ``WorkspaceClient`` so all Databricks
calls (discovery, Genie, codegen, MCP) execute with that user's *real*
permissions. We never cache a global client built from a user token.

When the header is absent (local dev, or not deployed as an App), we fall back
to the existing env/profile/service-principal configuration. The active mode is
reported as one of ``databricks_app_obo`` / ``user_workspace`` /
``service_principal`` so it is always visible (and never leaks the token).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

# Headers injected by the Databricks Apps platform when user authorization
# (OBO) is enabled. Case-insensitive lookups are handled by the resolver.
HEADER_ACCESS_TOKEN = "X-Forwarded-Access-Token"
HEADER_EMAIL = "X-Forwarded-Email"
HEADER_USER = "X-Forwarded-User"

MODE_OBO = "databricks_app_obo"
MODE_USER_WORKSPACE = "user_workspace"
MODE_SERVICE_PRINCIPAL = "service_principal"


@dataclass(frozen=True, slots=True)
class RequestAuth:
    """Resolved auth context for a single request.

    ``user_token`` is held only for the lifetime of the request and is never
    logged or returned in any API response.
    """

    mode: str
    host: str | None
    user_token: str | None = None
    user_email: str | None = None
    user_name: str | None = None

    @property
    def is_obo(self) -> bool:
        return self.mode == MODE_OBO and bool(self.user_token)

    @property
    def principal(self) -> str | None:
        return self.user_email or self.user_name


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup that works for dicts and Starlette Headers."""
    if headers is None:
        return None
    # Starlette Headers and most dict-likes support direct (case-insensitive) get.
    value = headers.get(name)
    if value:
        return value
    lowered = name.lower()
    for key, val in headers.items():
        if key.lower() == lowered:
            return val or None
    return None


def resolve_request_auth(
    headers: Mapping[str, str] | None,
    *,
    fallback_mode: str,
    fallback_host: str | None = None,
) -> RequestAuth:
    """Resolve the auth context for a request from forwarded headers.

    If ``X-Forwarded-Access-Token`` is present we run in OBO mode using that
    token. Otherwise we report the configured fallback mode (``user_workspace``
    or ``service_principal``) and the per-request client falls back to the
    existing env/profile/service-principal configuration.
    """
    headers = headers or {}
    token = _get_header(headers, HEADER_ACCESS_TOKEN)
    host = fallback_host or os.getenv("DATABRICKS_HOST")
    if token:
        return RequestAuth(
            mode=MODE_OBO,
            host=host,
            user_token=token,
            user_email=_get_header(headers, HEADER_EMAIL),
            user_name=_get_header(headers, HEADER_USER),
        )
    return RequestAuth(mode=fallback_mode or MODE_USER_WORKSPACE, host=host)
