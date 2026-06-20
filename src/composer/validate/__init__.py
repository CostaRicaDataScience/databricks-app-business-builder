"""Validation layer (Phase 5).

Closes the loop from DevHub's "Run and test deployed app": static checks on the
generated scaffold (deps, app.yaml, OBO scopes) plus an optional smoke test +
log triage of a deployed URL, and an autofix proposer that drives redeploy.
"""

from composer.validate.autofix import propose_fixes, should_redeploy
from composer.validate.runner import validate_app

__all__ = ["propose_fixes", "should_redeploy", "validate_app"]
