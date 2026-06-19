"""Tests for Databricks Apps OBO (on-behalf-of-user) per-request auth.

Verifies: the forwarded token is picked up and used to build a per-request
client; absence falls back cleanly to configured auth; tokens never appear in
logs or in ``/auth/status`` output.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from composer.databricks.client import DatabricksClient
from composer.databricks.obo import (
    HEADER_ACCESS_TOKEN,
    HEADER_EMAIL,
    MODE_OBO,
    RequestAuth,
    resolve_request_auth,
)
from composer.core.config import Settings
from modules.app.main import app

client = TestClient(app)

SECRET_TOKEN = "dapi-super-secret-user-token-DO-NOT-LOG"


def _settings(**overrides) -> Settings:
    base = dict(
        databricks_host="https://obo.example.databricks.com",
        databricks_token=None,
        databricks_profile=None,
        auth_mode="user_workspace",
        sp_client_id=None,
        sp_client_secret=None,
        foundation_model_endpoint="databricks-claude-sonnet",
        preferred_model="claude",
        fallback_model="fallback",
        appgen_dir=".appgen",
        output_root="./generated_apps",
        dry_run_default=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_resolver_detects_forwarded_token():
    auth = resolve_request_auth(
        {HEADER_ACCESS_TOKEN: SECRET_TOKEN, HEADER_EMAIL: "user@example.com"},
        fallback_mode="user_workspace",
        fallback_host="https://obo.example.databricks.com",
    )
    assert auth.mode == MODE_OBO
    assert auth.is_obo
    assert auth.user_token == SECRET_TOKEN
    assert auth.principal == "user@example.com"


def test_resolver_is_case_insensitive():
    auth = resolve_request_auth(
        {"x-forwarded-access-token": SECRET_TOKEN},
        fallback_mode="user_workspace",
    )
    assert auth.is_obo
    assert auth.user_token == SECRET_TOKEN


def test_resolver_falls_back_without_token():
    auth = resolve_request_auth(
        {},
        fallback_mode="service_principal",
        fallback_host="https://x",
    )
    assert auth.mode == "service_principal"
    assert not auth.is_obo
    assert auth.user_token is None


def test_for_request_builds_per_request_client_with_user_token():
    captured = {}

    def fake_workspace_client(host=None, token=None, **kwargs):
        captured["host"] = host
        captured["token"] = token
        ws = MagicMock()
        ws.current_user.me.return_value = MagicMock(
            user_name="user@example.com", display_name="User"
        )
        return ws

    auth = RequestAuth(
        mode=MODE_OBO,
        host="https://obo.example.databricks.com",
        user_token=SECRET_TOKEN,
        user_email="user@example.com",
    )
    with patch("composer.databricks.client.WorkspaceClient", fake_workspace_client):
        dbx = DatabricksClient.for_request(_settings(), auth)
        status = dbx.connection_status()

    # The forwarded user token was used to build the per-request client.
    assert captured["token"] == SECRET_TOKEN
    assert captured["host"] == "https://obo.example.databricks.com"
    assert status["auth_mode"] == MODE_OBO
    assert status["connected"] is True
    assert status["principal"] == "user@example.com"
    # No secrets leak into status output.
    assert SECRET_TOKEN not in json.dumps(status)


def test_for_request_without_token_falls_back_to_from_settings():
    auth = RequestAuth(mode="user_workspace", host="https://x", user_token=None)
    with patch("composer.databricks.client.WorkspaceClient", None):
        dbx = DatabricksClient.for_request(_settings(), auth)
    assert dbx.auth_mode_override is None
    assert dbx.workspace_client is None


def test_auth_status_endpoint_obo_mode_and_no_token_leak():
    fake_ws = MagicMock()
    fake_ws.current_user.me.return_value = MagicMock(
        user_name="obo-user@example.com", display_name="OBO User"
    )
    with patch(
        "composer.databricks.client.WorkspaceClient",
        return_value=fake_ws,
    ):
        res = client.get(
            "/auth/status",
            headers={
                HEADER_ACCESS_TOKEN: SECRET_TOKEN,
                HEADER_EMAIL: "obo-user@example.com",
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["auth_mode"] == MODE_OBO
    # Token must never appear anywhere in the response body.
    assert SECRET_TOKEN not in res.text


def test_auth_status_endpoint_without_headers_falls_back():
    res = client.get("/auth/status")
    assert res.status_code == 200
    data = res.json()
    # Default configured mode (not OBO) when no forwarded token is present.
    assert data["auth_mode"] in {"user_workspace", "service_principal"}


def test_forwarded_token_never_logged():
    """Even when logging connect attempts, the token must be redacted/absent."""
    auth = RequestAuth(
        mode=MODE_OBO,
        host="https://obo.example.databricks.com",
        user_token=SECRET_TOKEN,
        user_email="user@example.com",
    )
    fake_ws = MagicMock()
    fake_ws.current_user.me.return_value = MagicMock(
        user_name="user@example.com", display_name="User"
    )
    buf = io.StringIO()
    with redirect_stderr(buf):
        with patch(
            "composer.databricks.client.WorkspaceClient", return_value=fake_ws
        ):
            DatabricksClient.for_request(_settings(), auth).connection_status()
    assert SECRET_TOKEN not in buf.getvalue()
