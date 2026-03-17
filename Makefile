.PHONY: help bootstrap install lint type-check test test-unit test-smoke generate-data api docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

bootstrap: install generate-data ## Full project bootstrap
	@echo "✓ Bootstrap complete. Run 'make api' to start the API server."

install: ## Install dependencies
	pip install -e ".[dev]"

lint: ## Run linter (ruff)
	ruff check . --fix
	ruff format .

type-check: ## Run type checker (mypy)
	mypy apps/ services/ schemas/ ml/ --ignore-missing-imports

test: test-unit test-smoke ## Run all tests

test-unit: ## Run unit tests
	pytest tests/unit -v -m "not integration"

test-smoke: ## Run smoke tests
	pytest tests/smoke -v

generate-data: ## Generate synthetic datasets
	python data/synthetic/generate.py

api: ## Start FastAPI development server
	uvicorn apps.api.app.main:app --reload --host 0.0.0.0 --port 8000

docker-up: ## Start infrastructure (Postgres, MLflow, MinIO)
	docker compose -f infra/docker/docker-compose.yml up -d

docker-down: ## Stop infrastructure
	docker compose -f infra/docker/docker-compose.yml down

dbt-run: ## Run dbt models
	cd transform/dbt && dbt run --profiles-dir .

dbt-test: ## Run dbt tests
	cd transform/dbt && dbt test --profiles-dir .

dagster-dev: ## Start Dagster dev UI
	dagster dev -m orchestration.dagster.lenskart_dagster.definitions

clean: ## Clean generated files
	rm -rf data/synthetic/*.csv data/dev.duckdb
	rm -rf transform/dbt/target transform/dbt/dbt_packages
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

demo: bootstrap ## Run full demo: generate data, run tests, start API
	@echo "\n=== Running tests ==="
	$(MAKE) test
	@echo "\n=== Starting API server ==="
	@echo "Visit http://localhost:8000/docs for Swagger UI"
	$(MAKE) api
