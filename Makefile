.PHONY: help install lint format typecheck test check clean

help:
	@echo "Available targets:"
	@echo "  install    Sync dependencies (including dev)"
	@echo "  lint       Run ruff linter with autofix"
	@echo "  format     Format code with ruff"
	@echo "  typecheck  Run pyright type checker"
	@echo "  test       Run pytest"
	@echo "  check      Run lint, typecheck, and test"
	@echo "  clean      Remove caches and build artifacts"

install:
	uv sync

lint:
	uv run ruff check --fix src tests

format:
	uv run ruff format src tests

typecheck:
	uv run pyright

test:
	uv run pytest

check: lint typecheck test

clean:
	rm -rf .pytest_cache .ruff_cache dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
