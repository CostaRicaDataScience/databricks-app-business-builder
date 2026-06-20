"""DevHub template fetcher.

DevHub publishes a machine-readable index at developers.databricks.com/llms.txt
and a markdown page per template/recipe. This package fetches those on demand to
feed the Phase B build-out with canonical "what to build" context. All network
access is best-effort and degrades to ``None`` offline so the pipeline stays
deterministic and testable.
"""

from composer.devhub.fetcher import DevHubFetcher, fetch_template

__all__ = ["DevHubFetcher", "fetch_template"]
