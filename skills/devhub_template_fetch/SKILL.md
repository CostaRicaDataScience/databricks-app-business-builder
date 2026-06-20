# Skill: devhub_template_fetch

Function: app_builder

## When to use

When you need the canonical "what to build" for an archetype, fetch its DevHub
template markdown to feed the build-out.

## How it works

`src/composer/devhub/fetcher.py`:

- `DevHubFetcher(cache_dir, offline, timeout).fetch_template(url)` maps a DevHub
  template URL to its `.md` sibling and fetches it (stdlib urllib), caching to
  disk. Returns `None` on any failure.
- `fetch_index()` returns `developers.databricks.com/llms.txt`.
- `fetch_template(url, ...)` is a one-shot convenience.

## Rules

- Best-effort and offline-safe: never let a missing network break the pipeline.
- Cache under the app dir (`.devhub_cache/`) so repeated runs do not re-fetch.
- stdlib only - do not add an HTTP dependency.
