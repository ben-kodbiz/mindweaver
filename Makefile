# MindWeaver developer commands.
# Backend commands run through the `services/api` uv project; frontend via npm workspaces.

PYPROJECT := services/api

.PHONY: install test test-unit test-integration lint format typecheck \
        dev-api dev-web check precommit-install

install:
	uv sync --project $(PYPROJECT)
	npm install

test:
	cd $(PYPROJECT) && uv run pytest ../../tests

test-unit:
	cd $(PYPROJECT) && uv run pytest ../../tests/unit

test-integration:
	cd $(PYPROJECT) && uv run pytest ../../tests/integration

lint:
	uv run --project $(PYPROJECT) ruff check $(PYPROJECT)/src tests
	npm run web:lint

format:
	uv run --project $(PYPROJECT) ruff format $(PYPROJECT)/src tests
	npm run web:format

format-check:
	uv run --project $(PYPROJECT) ruff format --check $(PYPROJECT)/src tests
	npm run format:check -w @mindweaver/web

typecheck:
	uv run --project $(PYPROJECT) mypy $(PYPROJECT)/src
	npm run web:check

dev-api:
	cd $(PYPROJECT) && uv run uvicorn mindweaver.main:app --reload --port 8000

dev-web:
	npm run web:dev

check: test lint typecheck format-check

precommit-install:
	uvx pre-commit install
