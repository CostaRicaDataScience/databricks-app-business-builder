"""Fetch DevHub templates/recipes (best-effort, cached, offline-safe).

A DevHub template URL like
``https://developers.databricks.com/templates/genie-analytics-app`` has a
markdown sibling at ``.../genie-analytics-app.md``. We fetch that markdown to use
as canonical "what to build" context for the Phase B build-out.

Design constraints:
- stdlib only (urllib) so no new dependency is added.
- short timeout + broad except so a missing network never breaks the pipeline.
- optional on-disk cache so repeated runs do not re-fetch.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from composer.core.logging import log

DEVHUB_INDEX_URL = "https://developers.databricks.com/llms.txt"
_DEFAULT_TIMEOUT = 6.0


def _md_url(template_url: str) -> str:
    url = template_url.rstrip("/")
    return url if url.endswith(".md") else url + ".md"


def _http_get(url: str, timeout: float) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "business-builder/0.2"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            if getattr(resp, "status", 200) != 200:
                return None
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - network dependent
        log.info("devhub_fetch_failed", url=url, error=str(exc))
        return None


class DevHubFetcher:
    """Fetches DevHub markdown with an optional on-disk cache."""

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        offline: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout
        self.offline = offline
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{key}.md"

    def fetch_template(self, template_url: str) -> str | None:
        """Return the markdown for a DevHub template URL, or ``None``."""
        if not template_url:
            return None
        url = _md_url(template_url)
        cache_path = self._cache_path(url)
        if cache_path and cache_path.exists():
            try:
                return cache_path.read_text(encoding="utf-8")
            except Exception:  # pragma: no cover - best effort
                pass
        if self.offline:
            return None
        body = _http_get(url, self.timeout)
        if body and cache_path:
            try:
                cache_path.write_text(body, encoding="utf-8")
            except Exception:  # pragma: no cover - best effort
                pass
        return body

    def fetch_index(self) -> str | None:
        """Return the DevHub llms.txt index, or ``None`` when unavailable."""
        if self.offline:
            return None
        return _http_get(DEVHUB_INDEX_URL, self.timeout)


def fetch_template(
    template_url: str,
    *,
    cache_dir: str | Path | None = None,
    offline: bool = False,
    timeout: float = _DEFAULT_TIMEOUT,
) -> str | None:
    """Convenience one-shot fetch (see :class:`DevHubFetcher`)."""
    return DevHubFetcher(cache_dir, timeout=timeout, offline=offline).fetch_template(
        template_url
    )
