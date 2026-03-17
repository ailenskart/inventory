"""Dagster asset definitions for Lenskart data foundation pipeline."""

import os
import subprocess

from dagster import AssetExecutionContext, Output, asset

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DBT_PROJECT_DIR = os.path.join(PROJECT_ROOT, "transform", "dbt")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def _run_command(cmd: list[str], cwd: str) -> str:
    """Run a shell command and return output."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstderr: {result.stderr}")
    return result.stdout


# ─── Ingestion ───────────────────────────────────────────────────────────────

@asset(group_name="ingest", description="Generate synthetic CSV data files")
def synthetic_data(context: AssetExecutionContext) -> Output:
    """Generate synthetic datasets (50 stores, 1000 SKUs, 5 vendors, 365 days)."""
    output = _run_command(["python", "data/synthetic/generate.py"], cwd=PROJECT_ROOT)
    context.log.info(output)
    return Output(value={"status": "generated"}, metadata={"output": output})


@asset(group_name="ingest", deps=[synthetic_data], description="Copy CSVs to dbt seeds directory")
def load_seeds(context: AssetExecutionContext) -> Output:
    """Copy synthetic CSVs to dbt seeds directory."""
    output = _run_command(["python", "data/load_seeds.py"], cwd=PROJECT_ROOT)
    context.log.info(output)
    return Output(value={"status": "loaded"}, metadata={"output": output})


@asset(group_name="ingest", deps=[load_seeds], description="Load seed CSVs into DuckDB via dbt seed")
def dbt_seed(context: AssetExecutionContext) -> Output:
    """Run dbt seed to load CSVs into DuckDB raw schema."""
    output = _run_command(["dbt", "seed", "--profiles-dir", ".", "--full-refresh"], cwd=DBT_PROJECT_DIR)
    context.log.info(output)
    return Output(value={"status": "seeded"}, metadata={"output": output})


# ─── Transform ───────────────────────────────────────────────────────────────

@asset(group_name="transform", deps=[dbt_seed], description="Run dbt staging models")
def dbt_staging(context: AssetExecutionContext) -> Output:
    """Materialize staging views from raw sources."""
    output = _run_command(
        ["dbt", "run", "--profiles-dir", ".", "--select", "staging"],
        cwd=DBT_PROJECT_DIR,
    )
    context.log.info(output)
    return Output(value={"status": "staging_complete"}, metadata={"output": output})


@asset(group_name="transform", deps=[dbt_staging], description="Run dbt dimension models")
def dbt_dimensions(context: AssetExecutionContext) -> Output:
    """Materialize dimension tables."""
    output = _run_command(
        ["dbt", "run", "--profiles-dir", ".", "--select", "dimensions"],
        cwd=DBT_PROJECT_DIR,
    )
    context.log.info(output)
    return Output(value={"status": "dimensions_complete"}, metadata={"output": output})


@asset(group_name="transform", deps=[dbt_staging, dbt_dimensions], description="Run dbt intermediate models")
def dbt_intermediate(context: AssetExecutionContext) -> Output:
    """Materialize intermediate tables."""
    output = _run_command(
        ["dbt", "run", "--profiles-dir", ".", "--select", "intermediate"],
        cwd=DBT_PROJECT_DIR,
    )
    context.log.info(output)
    return Output(value={"status": "intermediate_complete"}, metadata={"output": output})


@asset(group_name="transform", deps=[dbt_intermediate, dbt_dimensions], description="Run dbt mart models")
def dbt_marts(context: AssetExecutionContext) -> Output:
    """Materialize mart tables (demand base, inventory position, vendor performance)."""
    output = _run_command(
        ["dbt", "run", "--profiles-dir", ".", "--select", "marts"],
        cwd=DBT_PROJECT_DIR,
    )
    context.log.info(output)
    return Output(value={"status": "marts_complete"}, metadata={"output": output})


# ─── Testing ─────────────────────────────────────────────────────────────────

@asset(group_name="quality", deps=[dbt_marts], description="Run dbt tests")
def dbt_tests(context: AssetExecutionContext) -> Output:
    """Run all dbt tests (schema contracts + custom business rules)."""
    output = _run_command(
        ["dbt", "test", "--profiles-dir", "."],
        cwd=DBT_PROJECT_DIR,
    )
    context.log.info(output)
    return Output(value={"status": "tests_passed"}, metadata={"output": output})


@asset(group_name="quality", deps=[dbt_marts], description="Run data validation checks")
def data_validation(context: AssetExecutionContext) -> Output:
    """Run source and mart validation checks."""
    output = _run_command(["python", "data/validate.py"], cwd=PROJECT_ROOT)
    context.log.info(output)
    return Output(value={"status": "validation_passed"}, metadata={"output": output})


# ─── ML (downstream, placeholder) ───────────────────────────────────────────

@asset(group_name="ml", deps=[dbt_marts], description="Generate demand forecasts")
def demand_forecast(context: AssetExecutionContext) -> Output:
    """Generate demand forecasts at SKU x Store x Week."""
    # TODO: Wire to ml/forecasting pipeline
    context.log.info("Demand forecast placeholder — wire to ml/forecasting/baseline.py")
    return Output(value={"status": "placeholder", "forecasts_generated": 0})


@asset(group_name="ml", deps=[dbt_marts], description="Update store cluster assignments")
def store_clustering(context: AssetExecutionContext) -> Output:
    """Update store cluster assignments based on recent behavior."""
    # TODO: Wire to ml/features clustering
    context.log.info("Store clustering placeholder — wire to ml/features/store_features.py")
    return Output(value={"status": "placeholder", "clusters": 0})


# ─── Optimization (downstream, placeholder) ──────────────────────────────────

@asset(group_name="optimization", deps=[demand_forecast], description="Generate replenishment plan")
def replenishment_plan(context: AssetExecutionContext) -> Output:
    """Generate replenishment recommendations."""
    # TODO: Wire to services/replenishment
    return Output(value={"status": "placeholder", "recommendations": 0})


@asset(group_name="optimization", deps=[demand_forecast, store_clustering], description="Generate assortment plan")
def assortment_plan(context: AssetExecutionContext) -> Output:
    """Generate assortment optimization recommendations."""
    # TODO: Wire to services/assortment
    return Output(value={"status": "placeholder", "recommendations": 0})


@asset(group_name="optimization", deps=[demand_forecast], description="Generate transfer plan")
def transfer_plan(context: AssetExecutionContext) -> Output:
    """Generate inter-store transfer recommendations."""
    # TODO: Wire to services/transfers
    return Output(value={"status": "placeholder", "transfers": 0})


@asset(group_name="vendor", deps=[demand_forecast, replenishment_plan], description="Generate PO suggestions")
def purchase_order_suggestions(context: AssetExecutionContext) -> Output:
    """Generate automated PO suggestions."""
    # TODO: Wire to services/purchase_orders
    return Output(value={"status": "placeholder", "po_suggestions": 0})
