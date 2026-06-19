.PHONY: install run test cli composer-flow
install:
	uv pip install -e ".[dev]"
run:
	uvicorn modules.app.main:app --reload
test:
	pytest -q
cli:
	python -m modules.app.cli --help
composer-flow:
	composer --help
