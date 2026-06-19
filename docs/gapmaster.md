# Gapmaster — Unified Plan Tracking

## Gaps

| ID | Gap | Severity | Status | Closure plan |
|----|-----|----------|--------|--------------|
| G1 | Databricks SDK calls are partially mocked in discovery/genie/deploy paths | high | in_progress | Replace stubs with concrete SDK operations and add mocked tests for each API adapter |
| G2 | Foundation Model integration uses deterministic planning fallback | high | in_progress | Add endpoint invocation + structured response parser + retry/fallback logic |
| G3 | Streamlit intake UI is minimal and not yet checkpoint-driven | medium | open | Add guided stateful workflow with explicit approval checkpoints |

## Risks

| ID | Risk | Likelihood | Impact | Mitigation | Status |
|----|------|------------|--------|------------|--------|
| R1 | Workspace permission variance breaks write actions | high | high | Enforce preflight before writes and keep dry-run default | mitigated |
| R2 | LLM output drift causes non-deterministic generation | medium | high | Use schema validation + artifact traceability + reproducibility checks | in_progress |
| R3 | Migration from `modules/` to `src/composer/` may break compatibility | medium | medium | Keep compatibility API and migrate incrementally per phase | in_progress |

## Technical debt

| ID | Debt | Introduced in | Interest | Payoff plan |
|----|------|---------------|----------|-------------|
| D1 | Dual orchestration logic across `modules/app/services.py` and `src/composer/` | migration phase | medium | Move API to composer service directly and keep thin compatibility adapters only |

## Security and supply-chain

| Dependency | Risk | Action |
|------------|------|--------|
| `databricks-sdk` | Token misuse in logs/config | Maintain redaction and add stricter secret scanning in CI |
| `streamlit` | Client-side intake exposure | Keep server-side validation and no secret rendering |