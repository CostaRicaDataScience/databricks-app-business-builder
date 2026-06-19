# Blueprint — Databricks App Business Builder

```yaml
blueprint_version: 2
complexity: large
oss_first: true
architecture: unified_composer_appgen
```

## Vision

Build an OSS product that turns analyst requirements into deployable Databricks Apps:

1. Intake and requirement capture.
2. Discovery of tables/genies and metadata quality.
3. Approval-gated enrichment and genie actions.
4. Structured planning and deterministic code generation.
5. Preflight, deploy, and tagging governance.

## Chosen architecture

- Runtime package: `src/composer/`.
- Compatibility layer: `modules/` (temporary during migration).
- Artifact source of truth: `.appgen/*.yaml`.
- LLM strategy: Databricks Foundation Model APIs, Claude preferred + fallback.
- Deployment: Databricks Apps API / DAB-compatible flow.

## Delivery and quality

- CI pipeline: lint + tests on push/PR.
- Dry-run defaults for write operations.
- Approval records stored in `.appgen/approvals/`.
- Release assets: LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, examples.

## Reference docs

- Design: `docs/design.md`
- Gaps and risks: `docs/gapmaster.md`
- Contracts: `contracts/base-contracts.yaml`