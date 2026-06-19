# Contributing

## Setup

1. Create a virtualenv.
2. Install dependencies:
   - `uv pip install --python .venv/bin/python -e ".[dev]"`
3. Run tests:
   - `pytest -q`

## Development workflow

- Keep changes scoped to one capability per PR.
- Add tests for new behavior.
- Preserve `.appgen` artifact compatibility.
- Use dry-run defaults for write operations.

## Pull requests

- Include a short problem statement and test evidence.
- Mention any Databricks permissions required for validation.
