.PHONY: help setup up down logs psql minio lint format test test-fast quality \
	simulate seed bronze silver gold pipeline ops platform-kpis \
	tf-init tf-plan tf-apply tf-apply-stage1 tf-apply-all tf-destroy tf-output dbx-kill dbx-deploy dbx-run dashboard diagrams exports clean

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

diagrams:  ## Re-render the architecture diagram + animated walkthrough from HTML
	cd docs/diagrams && ../../.venv/bin/python render_static.py
	cd docs/diagrams && ../../.venv/bin/python render_pipeline_gif.py \
	  -o pipeline_animated.webm --duration 47 --fps 10
	cd docs/diagrams && ../../.venv/bin/python render_pipeline_gif.py \
	  -o pipeline_animated.mp4 --duration 47 --fps 10
	cd docs/diagrams && ../../.venv/bin/python render_pipeline_gif.py \
	  -o pipeline_animated.gif --duration 47 --fps 6 --scale-width 1200
	@ls -lh docs/diagrams/pipeline_a*

dashboard:  ## Run the Streamlit dashboard (reads exports/, needs no Azure)
	.venv/bin/streamlit run app/Home.py

exports:  ## Download the Gold Parquet snapshot the dashboard reads
	./scripts/fetch-exports.sh

dbx-deploy:  ## Build+upload the wheel, import notebooks, sync the job
	./scripts/deploy-databricks.sh

dbx-run:  ## Deploy, then run the medallion job and wait for it
	./scripts/deploy-databricks.sh --run

quality:  ## Run data-quality checks against the real lake
	$(PY) -m factorypulse.quality.checks --fail-fast

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

pipeline:  ## Run the tracked end-to-end medallion pipeline
	.venv/bin/factorypulse run

ops:  ## Show recent pipeline-run records
	.venv/bin/factorypulse ops

platform-kpis:  ## Show operational platform KPIs
	.venv/bin/factorypulse platform-kpis

tf-init:  ## Initialise Terraform
	cd infra/terraform && terraform init

tf-plan:  ## Show what Terraform would change
	cd infra/terraform && terraform plan

tf-apply:  ## Build/update the Azure platform
	cd infra/terraform && terraform apply
	./scripts/azure-env.sh

tf-apply-stage1:  ## First-time only: bootstrap Azure Databricks workspace
	cd infra/terraform && terraform apply -target=azurerm_databricks_workspace.main

tf-apply-all: tf-apply-stage1  ## First-time Databricks deployment in two stages
	cd infra/terraform && terraform apply
	./scripts/azure-env.sh

dbx-kill:  ## Terminate every active Databricks all-purpose cluster
	@databricks clusters list --output json | jq -r '.[] | select(.state == "RUNNING" or .state == "PENDING" or .state == "RESTARTING" or .state == "RESIZING") | .cluster_id' | xargs -r -n1 databricks clusters delete --cluster-id
	@echo "all interactive Databricks clusters terminated"

tf-destroy:  ## DESTROY all Azure resources (billing stops)
	cd infra/terraform && terraform destroy

tf-output:  ## Show Terraform outputs
	cd infra/terraform && terraform output

clean:  ## Remove generated artifacts
	rm -rf spark-warehouse metastore_db derby.log .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
