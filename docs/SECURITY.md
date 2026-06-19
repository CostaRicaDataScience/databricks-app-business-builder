# Security & Auth — Databricks App business builder

_Context-aware proposal. Nothing here is force-installed; adjust as needed._

**Rationale:** Proposed for a backend_service project from requirement signals. AuthN: JWT sessions (Authlib / PyJWT) (matched signals ['api', 'backend']) | AuthZ: OpenFGA | Security tooling: Gitleaks, Semgrep, Dependabot / Renovate, Husky + lint-staged

## Authentication & Authorization

| Approach | Kind | Role | License | Why |
|----------|------|------|---------|-----|
| [JWT sessions (Authlib / PyJWT)](https://github.com/lepture/authlib) | token_auth | PRIMARY | BSD-3-Clause | matched signals ['api', 'backend'] |
| [Keycloak](https://github.com/keycloak/keycloak) | identity_provider | alternative | Apache-2.0 | alternative — matched [] |
| [Ory (Kratos + Hydra)](https://github.com/ory) | identity_provider | alternative | Apache-2.0 | alternative — matched [] |
| [OpenFGA](https://github.com/openfga/openfga) | authorization | authorization | Apache-2.0 | authorization layer — matched []; pairs with the AuthN above |

### Packages for the primary approach

- **JWT sessions (Authlib / PyJWT)** → `authlib` (*) on `python_backend`

## Security / CI tooling (separate from runtime deps)

| Tool | Kind | Stage | License | Why |
|------|------|-------|---------|-----|
| [Gitleaks](https://github.com/gitleaks/gitleaks) | secret_scanning | `ci` | MIT | baseline — recommended for every project |
| [Semgrep](https://github.com/semgrep/semgrep) | sast | `ci` | LGPL-2.1 ⚠️ review | baseline — recommended for every project |
| [Dependabot / Renovate](https://github.com/renovatebot/renovate) | dependency_updates | `ci` | AGPL-3.0 ⚠️ review | baseline — recommended for every project |
| [Husky + lint-staged](https://github.com/typicode/husky) | git_hooks | `pre_commit` | MIT | matched signals ['frontend'] |

> Runtime libraries live in `config/dependencies.yaml`. The tools above are wired into CI / pre-commit / runtime as indicated by **Stage**, not bundled as application dependencies.
