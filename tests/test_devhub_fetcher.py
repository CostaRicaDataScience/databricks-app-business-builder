"""Tests for the DevHub fetcher (Phase 3) - mocked HTTP, offline-safe."""

from __future__ import annotations

import composer.devhub.fetcher as fetcher_mod
from composer.devhub.fetcher import DevHubFetcher, _md_url


def test_md_url_appends_md():
    assert _md_url("https://developers.databricks.com/templates/genie-analytics-app") == (
        "https://developers.databricks.com/templates/genie-analytics-app.md"
    )
    assert _md_url("https://x/y.md") == "https://x/y.md"


def test_fetch_uses_cache_and_single_http_call(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_http_get(url, timeout):
        calls["n"] += 1
        return "# Genie Analytics App\nbuild a genie app"

    monkeypatch.setattr(fetcher_mod, "_http_get", fake_http_get)
    f = DevHubFetcher(cache_dir=tmp_path)
    url = "https://developers.databricks.com/templates/genie-analytics-app"
    first = f.fetch_template(url)
    second = f.fetch_template(url)
    assert "Genie" in first
    assert first == second
    # second call served from cache -> only one HTTP hit
    assert calls["n"] == 1


def test_offline_returns_none_without_cache(tmp_path, monkeypatch):
    def boom(url, timeout):  # pragma: no cover - must not be called
        raise AssertionError("network must not be used when offline")

    monkeypatch.setattr(fetcher_mod, "_http_get", boom)
    f = DevHubFetcher(cache_dir=tmp_path, offline=True)
    assert f.fetch_template("https://developers.databricks.com/templates/ai-chat-app") is None


def test_fetch_failure_degrades_to_none(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher_mod, "_http_get", lambda url, timeout: None)
    f = DevHubFetcher(cache_dir=tmp_path)
    assert f.fetch_template("https://developers.databricks.com/templates/ai-chat-app") is None
