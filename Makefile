.PHONY: help setup up down logs psql minio lint format test test-fast \
	simulate seed bronze silver gold pipeline clean

SHELL := /bin/bash
PY := .venv/bin/python

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv and install the project
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	.venv/bin/pre-commit install

up:  ## Start Postgres + MinIO
	docker compose -f infra/docker/docker-compose.yml up -d
	@echo "MinIO console: http://localhost:9001  (minioadmin/minioadmin)"

down:  ## Stop the stack (keeps volumes)
	docker compose -f infra/docker/docker-compose.yml down

logs:  ## Tail container logs
	docker compose -f infra/docker/docker-compose.yml logs -f

psql:  ## Open a psql shell
	docker exec -it fp-postgres psql -U factorypulse -d factorypulse

lint:  ## Lint
	.venv/bin/ruff check src tests

format:  ## Auto-format and auto-fix
	.venv/bin/ruff format src tests
	.venv/bin/ruff check --fix src tests

test:  ## Run all tests (slow — starts Spark)
	.venv/bin/pytest

test-fast:  ## Run only tests that do not need Spark
	.venv/bin/pytest -m "not slow"

simulate:  ## Generate telemetry (override: make simulate ROWS=100000)
	$(PY) -m factorypulse.simulator.generate --rows $${ROWS:-10000000}

seed:  ## Seed Postgres with reference data
	$(PY) -m factorypulse.simulator.seed_postgres

bronze:  ## Run the bronze layer
	$(PY) -m factorypulse.pipeline.bronze

silver:  ## Run the silver layer
	$(PY) -m factorypulse.pipeline.silver

gold:  ## Run the gold layer
	$(PY) -m factorypulse.pipeline.gold

pipeline: bronze silver gold  ## Run the full medallion pipeline

clean:  ## Remove generated artifacts
	rm -rf spark-warehouse metastore_db derby.log .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
