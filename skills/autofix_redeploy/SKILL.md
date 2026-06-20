# Skill: autofix_redeploy

Function: app_builder

## When to use

After validation finds failures, propose concrete fixes and decide whether a
redeploy is warranted.

## How it works

`src/composer/validate/autofix.py`:

- `propose_fixes(validation_report)` -> `[{check, detail, fix}]` mapping each
  failed check to a remediation (missing SDK, invalid app.yaml, missing scopes,
  smoke failure, log errors).
- `should_redeploy(validation_report)` -> True when an actionable failure
  (deps, app.yaml, smoke, logs) could be resolved by redeploying.

## Rules

- Propose, do not auto-apply to a live deploy without approval.
- After fixing, redeploy and re-validate until green.
