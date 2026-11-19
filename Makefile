UV_RUN := uv run --locked --all-packages

.PHONY: help format format-check lint lint-fix type test check fix

help:
	@echo "make fix     Apply Ruff fixes and format the code"
	@echo "make check   Check formatting, lint, types, and tests"

format:
	$(UV_RUN) ruff format .

format-check:
	$(UV_RUN) ruff format --check .

lint:
	$(UV_RUN) ruff check .

lint-fix:
	$(UV_RUN) ruff check --fix .

type:
	$(UV_RUN) mypy

test:
	$(UV_RUN) pytest

check: format-check lint type test

fix: lint-fix
	$(MAKE) format
