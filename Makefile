.PHONY: help bootstrap install lint type-check test test-unit test-smoke test-data test-integration generate-data load-seeds api docker-up docker-down dbt-seed dbt-run dbt-test dbt-full validate-data dagster-dev clean demo demo-e2e data-pipeline forecast-train forecast-predict forecast-evaluate replenishment-run replenishment-simulate assortment-optimize assortment-simulate lifecycle-run transfer-run po-generate

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

bootstrap: install generate-data ## Full project bootstrap
	@echo "Bootstrap complete. Run 'make api' to start the API server."

install: ## Install dependencies
	pip install -e ".[dev]"

lint: ## Run linter (ruff)
	ruff check . --fix
	ruff format .

type-check: ## Run type checker (mypy)
	mypy apps/ services/ schemas/ ml/ --ignore-missing-imports

# ─── Testing ─────────────────────────────────────────────────────────────────

test: test-unit test-smoke ## Run all tests

test-unit: ## Run unit tests
	pytest tests/unit -v -m "not integration"

test-smoke: ## Run smoke tests (API + data + full flow)
	pytest tests/smoke -v

test-data: ## Run data foundation tests (generate → dbt → validate)
	pytest tests/smoke/test_data_foundation.py -v

test-integration: ## Run integration tests (requires data foundation)
	pytest tests/integration -v -m integration

test-full-flow: ## Run full-flow integration smoke test
	pytest tests/smoke/test_full_flow.py -v

# ─── Data Foundation ─────────────────────────────────────────────────────────

generate-data: ## Generate synthetic datasets (50 stores, 1000 SKUs, 365 days)
	python data/synthetic/generate.py

load-seeds: ## Copy synthetic CSVs to dbt seeds directory
	python data/load_seeds.py

dbt-seed: ## Load seed CSVs into DuckDB via dbt
	cd transform/dbt && dbt seed --profiles-dir . --full-refresh

dbt-run: ## Run all dbt models (staging → dims → intermediate → marts)
	cd transform/dbt && dbt run --profiles-dir .

dbt-test: ## Run dbt schema + custom tests
	cd transform/dbt && dbt test --profiles-dir .

dbt-full: generate-data load-seeds dbt-seed dbt-run dbt-test ## Full dbt pipeline end-to-end
	@echo "Data foundation pipeline complete."

validate-data: ## Run data validation checks against DuckDB
	python data/validate.py

data-pipeline: dbt-full validate-data ## Full data pipeline + validation
	@echo "Data pipeline + validation complete."

# ─── Services ────────────────────────────────────────────────────────────────

api: ## Start FastAPI development server (http://localhost:8000/docs)
	uvicorn apps.api.app.main:app --reload --host 0.0.0.0 --port 8000

docker-up: ## Start infrastructure (Postgres, MLflow, MinIO)
	docker compose -f infra/docker/docker-compose.yml up -d

docker-down: ## Stop infrastructure
	docker compose -f infra/docker/docker-compose.yml down

dagster-dev: ## Start Dagster dev UI
	dagster dev -m orchestration.dagster.lenskart_dagster.definitions

# ─── Forecasting ─────────────────────────────────────────────────────────────

forecast-train: ## Train demand forecast models (requires data foundation)
	python -m ml.forecasting.train

forecast-predict: ## Run batch forecast inference
	python -m ml.forecasting.predict

forecast-evaluate: ## Evaluate forecast model quality
	python -m ml.forecasting.evaluate --output data/eval_report.json

# ─── Lifecycle Intelligence ──────────────────────────────────────────────────

lifecycle-run: ## Run lifecycle classification pipeline
	python -m services.lifecycle.pipeline

lifecycle-v2: ## Run lifecycle with v2 survival scoring
	python -m services.lifecycle.pipeline --v2-scoring

# ─── Replenishment ───────────────────────────────────────────────────────────

replenishment-run: ## Run daily replenishment pipeline
	python -m services.replenishment.pipeline

replenishment-simulate: ## Simulate daily vs weekly replenishment
	python -m services.replenishment.simulation --weeks 12

# ─── Assortment ──────────────────────────────────────────────────────────────

assortment-optimize: ## Run assortment optimization pipeline
	python -m services.assortment.pipeline

assortment-simulate: ## Simulate heuristic vs optimized assortment
	python -m services.assortment.simulation --capacity 80 --n-skus 200

# ─── Transfers ───────────────────────────────────────────────────────────────

transfer-run: ## Run inter-store transfer optimization
	python -m services.transfers.pipeline

# ─── Purchase Orders ─────────────────────────────────────────────────────────

po-generate: ## Generate PO recommendations from replenishment needs
	python -m services.purchase_orders.pipeline

# ─── Demo ────────────────────────────────────────────────────────────────────

demo: bootstrap dbt-full validate-data ## Full demo: bootstrap → dbt → validate → tests → API
	@echo "\n=== Running tests ==="
	$(MAKE) test
	@echo "\n=== Starting API server ==="
	@echo "Visit http://localhost:8000/docs for Swagger UI"
	$(MAKE) api

demo-e2e: ## Run end-to-end demo script (all modules)
	python scripts/demo_e2e.py

demo-e2e-quick: ## Run e2e demo skipping data foundation (requires prior make dbt-full)
	python scripts/demo_e2e.py --skip-data-foundation

# ─── Cleanup ─────────────────────────────────────────────────────────────────

clean: ## Clean generated files
	rm -rf data/synthetic/*.csv data/dev.duckdb
	rm -rf transform/dbt/seeds/*.csv
	rm -rf transform/dbt/target transform/dbt/dbt_packages transform/dbt/logs
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
