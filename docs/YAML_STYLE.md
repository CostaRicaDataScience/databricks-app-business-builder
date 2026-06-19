# YAML Style & Formatting Rules

These are the **explicit, enforced** rules for every YAML file the bootstrapper
produces or normalizes. The machine-readable source of truth is
[`yaml-style.yaml`](./yaml-style.yaml); the standardizer loads it and applies it
deterministically (same input -> same output).

## Formatting
- **Indentation:** 2 spaces for mappings, 4 for sequences, dash offset 2.
- **Block style only** — never inline flow style (`{a: 1, b: 2}`).
- **Quotes preserved**; files end with a single trailing newline.
- **Max line length:** 100 characters.

## Key ordering
- Top-level: `version`, `name`, `description`, `metadata` (when present).
- **Dependency item:** `name`, `version`, `source`, `license` (extras sorted after).
- **Agent spec:** `name`, `prompt`/`instructions`, `executor`, `os_env`,
  `terminals`, `tools`, `policies`.
- Dependency lists are sorted alphabetically by `name` and de-duplicated.

## Required keys
- **Dependencies doc:** `version`, `dependencies`.
- **Dependency item:** `name`, `version`, `license`.
- **Agent spec:** `name`, `executor`.

## Defaults applied (and flagged)
- Missing dependency `version` -> `"*"` (flagged as a warning to pin later).
- Missing `license` -> `UNKNOWN` (flagged for human review).

## License policy
- **Permissive (allow):** MIT, Apache-2.0, BSD-3-Clause, BSD-2-Clause, ISC.
- **Needs review (flag, never auto-deny):** LGPL-2.1, GPL-3.0, AGPL-3.0,
  MPL-2.0, UNKNOWN.

## Validation loop
`lint -> auto_fix -> validate`, failing on missing required keys or invalid
structure, and always emitting a **before/after diff report** for auditability.

> Enforce from the CLI: `bootstrapper format-yaml <file> --write`
