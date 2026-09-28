# DrillSage: single entry point for every routine task. Run `make help`.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

API     := apps/api
WEB     := apps/web
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: help
help: ## List targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[33m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.env:
	cp .env.example .env

# ---------------------------------------------------------------- setup
.PHONY: setup
setup: .env ## Install toolchains' dependencies and git hooks
	cd $(API) && uv sync
	pnpm install --frozen-lockfile
	uv tool run pre-commit install

# ---------------------------------------------------------------- database
.PHONY: db-up db-down db-reset migrate
db-up: .env ## Start Postgres (pgvector) and wait until healthy
	$(COMPOSE) up -d --wait db

db-down: ## Stop Postgres (data is kept)
	$(COMPOSE) stop db

db-reset: .env ## Destroy and recreate the database volume, then migrate
	$(COMPOSE) down -v
	$(MAKE) db-up migrate

migrate: ## Apply database migrations
	cd $(API) && uv run alembic upgrade head

# ---------------------------------------------------------------- data
.PHONY: data data-fetch data-load data-qc eval eval-parser
data: data-fetch db-up migrate data-load eval-parser data-qc extract snapshot ## Fetch, load Postgres (idempotent), data reports, field snapshot

data-fetch: ## Download the pinned DDR mirror and Sodir tables into data/raw
	cd $(API) && uv run drillsage-data fetch

data-load: ## Load data/raw into Postgres; re-running changes nothing
	cd $(API) && uv run drillsage-data load

data-qc: ## Per-wellbore data QC report -> eval/reports/data_qc.{md,json}
	cd $(API) && uv run drillsage-data qc

eval-parser: ## Parser fidelity report -> eval/reports/parser_fidelity.{md,json}
	cd $(API) && uv run drillsage-data fidelity

eval: eval-parser extract ## Every evaluation report (later phases add retrieval, backtest)

.PHONY: gold-sample gold-eval
gold-sample: ## Stratified gold sample for hand labelling -> data/processed/gold (open eval/labeling/label.html)
	cd $(API) && uv run drillsage-data gold-sample

gold-eval: ## Score extraction tiers against eval/gold/labels-gold-v1.json -> eval/reports/extraction_gold.*
	cd $(API) && uv run drillsage-data gold-eval

.PHONY: extract llm-estimate snapshot
snapshot: ## Field snapshot for the web cockpit, straight from raw files (no database)
	cd $(API) && uv run drillsage-data snapshot

extract: ## Rebuild events (rules + stored LLM results; never calls a model) + extraction report
	cd $(API) && uv run drillsage-data extract

llm-estimate: ## Cost estimate for the LLM extraction pilot (never calls a model)
	cd $(API) && uv run drillsage-data llm-estimate --pilot 50

# ---------------------------------------------------------------- run
.PHONY: dev ui api web
dev: db-up migrate ## Run API (:8000) and web (:3000) with reload; Ctrl-C stops both
	@trap 'kill 0' INT TERM EXIT; \
	  ( cd $(API) && uv run uvicorn drillsage.api.app:create_app --factory --reload --port 8000 ) & \
	  ( cd $(WEB) && pnpm dev --port 3000 ) & \
	  wait

ui: ## API (:8000) + web (:3000) from the field snapshot; no database or Docker needed
	@test -f data/processed/web/field-snapshot.json || $(MAKE) snapshot
	@trap 'kill 0' INT TERM EXIT; \
	  ( cd $(API) && uv run uvicorn drillsage.api.app:create_app --factory --reload --port 8000 ) & \
	  ( cd $(WEB) && pnpm dev --port 3000 ) & \
	  wait

api: ## Run only the API with reload
	cd $(API) && uv run uvicorn drillsage.api.app:create_app --factory --reload --port 8000

web: ## Run only the web app with reload
	cd $(WEB) && pnpm dev --port 3000

# ---------------------------------------------------------------- quality
.PHONY: lint format test test-api test-web cov api-client api-client-check build
lint: ## Static checks: ruff, mypy, eslint, tsc, prettier
	cd $(API) && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd $(WEB) && pnpm lint && pnpm typecheck
	pnpm format:check

format: ## Auto-format everything
	cd $(API) && uv run ruff check --fix . && uv run ruff format .
	pnpm format

test: test-api test-web ## All tests (API integration tests skip when the DB is down)

test-api:
	cd $(API) && uv run pytest

test-web:
	cd $(WEB) && pnpm test

cov: ## API tests with coverage report
	cd $(API) && uv run pytest --cov --cov-report=term-missing

api-client: ## Regenerate the typed web client from the API's OpenAPI schema
	cd $(API) && uv run python scripts/export_openapi.py ../web/src/lib/api/openapi.json
	cd $(WEB) && pnpm api:types

api-client-check: api-client ## Fail if the committed web client is stale
	git diff --exit-code -- $(WEB)/src/lib/api/

build: ## Production build of the web app
	cd $(WEB) && pnpm build
