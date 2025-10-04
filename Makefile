.PHONY: install test lint format type-check ci-check setup-pre-commit

install:
	uv pip install -e ".[dev]"

test:
	uv run pytest --cov=src/loxone_mcp --cov-report=xml

lint:
	uv run ruff check src/ tests/

format:
	uv run black --check src/ tests/

type-check:
	uv run mypy src/

ci-check: lint format type-check test

setup-pre-commit:
	uv run pre-commit install
