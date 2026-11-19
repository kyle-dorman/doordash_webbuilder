UV_RUN := uv run --locked --all-packages

.PHONY: help format format-check lint lint-fix type test check fix stories shopper-browser

help:
	@echo "make fix     Apply Ruff fixes and format the code"
	@echo "make check   Check formatting, lint, types, and tests"
	@echo "make stories Generate Thai Peacock and run its five Playwright stories"

shopper-browser:
	$(UV_RUN) playwright install --only-shell chromium

stories: shopper-browser
	$(UV_RUN) run-shopper-stories

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

test: shopper-browser
	$(UV_RUN) pytest

check: format-check lint type test

fix: lint-fix
	$(MAKE) format
