"""Dagster asset definitions for the Lenskart Retail Intelligence Platform.

Full daily flow:
  ingest → validate → transform → feature build → forecast →
  lifecycle → replenishment → assortment → transfers → vendor planning → PO recommendations
"""

import os
import subprocess

import pandas as pd
from dagster import AssetExecutionContext, Output, asset

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DBT_PROJECT_DIR = os.path.join(PROJECT_ROOT, "transform", "dbt")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "dev.duckdb")


def _run_command(cmd: list[str], cwd: str) -> str:
    """Run a shell command and return output."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nstderr: {result.stderr}")
    return result.stdout


def _ensure_sys_path():
    """Ensure PROJECT_ROOT is on sys.path for imports."""
    import sys
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)


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


# ─── Quality ─────────────────────────────────────────────────────────────────

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


# ─── Feature Engineering ─────────────────────────────────────────────────────

@asset(group_name="ml", deps=[dbt_marts], description="Materialize features to Feast offline store")
def feature_materialization(context: AssetExecutionContext) -> Output:
    """Materialize demand and inventory features for the feature store."""
    _ensure_sys_path()
    from ml.forecasting.config import ForecastConfig
    from ml.forecasting.data_loader import load_demand_data, load_inventory_data
    from ml.forecasting.feature_store import materialize_features
    from ml.forecasting.features import generate_all_features

    config = ForecastConfig(db_path=DB_PATH)
    demand_df = load_demand_data(config)
    features_df = generate_all_features(demand_df, config)
    inventory_df = load_inventory_data(config)

    materialize_features(
        demand_df=features_df,
        inventory_df=inventory_df,
        output_dir=os.path.join(DATA_DIR, "features"),
    )

    context.log.info(f"Materialized {len(features_df)} demand feature rows, "
                     f"{len(inventory_df)} inventory rows")
    return Output(
        value={"status": "materialized"},
        metadata={"demand_rows": len(features_df), "inventory_rows": len(inventory_df)},
    )


@asset(group_name="ml", deps=[dbt_marts], description="Update store cluster assignments")
def store_clustering(context: AssetExecutionContext) -> Output:
    """Update store cluster assignments based on recent behavior."""
    context.log.info("Store clustering: using static cluster assignments from dim_store")
    return Output(value={"status": "static_clusters"})


# ─── Forecasting ─────────────────────────────────────────────────────────────

@asset(group_name="ml", deps=[dbt_marts], description="Train demand forecast models")
def demand_forecast_train(context: AssetExecutionContext) -> Output:
    """Train demand forecast models with cross-validation and model selection."""
    _ensure_sys_path()
    from ml.forecasting.config import ForecastConfig
    from ml.forecasting.train import run_training_pipeline

    config = ForecastConfig(db_path=DB_PATH)
    result = run_training_pipeline(config)

    n_forecasts = len(result.get("forecasts", []))
    best_model = "N/A"
    best_wmape = -1
    report = result.get("report", {})
    if report.get("model_ranking"):
        best_model = report["model_ranking"][0]["model"]
        best_wmape = report["model_ranking"][0].get("wmape", -1)

    context.log.info(f"Training complete: {n_forecasts} forecasts, "
                     f"best model={best_model}, WMAPE={best_wmape:.4f}")

    return Output(
        value={"status": result.get("status"), "best_model": best_model},
        metadata={"best_model": best_model, "best_wmape": best_wmape},
    )


@asset(group_name="ml", deps=[demand_forecast_train], description="Generate batch demand forecasts")
def demand_forecast(context: AssetExecutionContext) -> Output:
    """Run batch inference to generate demand forecasts for all active SKU x Store."""
    _ensure_sys_path()
    from ml.forecasting.config import ForecastConfig
    from ml.forecasting.predict import run_inference_pipeline

    config = ForecastConfig(db_path=DB_PATH)
    forecasts = run_inference_pipeline(config, write_to_db=True)

    n_forecasts = len(forecasts)
    n_stores = int(forecasts["store_id"].nunique()) if not forecasts.empty else 0
    n_skus = int(forecasts["sku_id"].nunique()) if not forecasts.empty else 0

    context.log.info(f"Inference complete: {n_forecasts} forecasts, "
                     f"{n_stores} stores, {n_skus} SKUs")

    return Output(
        value={"status": "success", "forecasts_generated": n_forecasts},
        metadata={"n_forecasts": n_forecasts, "n_stores": n_stores, "n_skus": n_skus},
    )


# ─── Lifecycle Intelligence ──────────────────────────────────────────────────

@asset(group_name="intelligence", deps=[demand_forecast], description="Classify SKU lifecycle stages")
def lifecycle_classification(context: AssetExecutionContext) -> Output:
    """Run lifecycle classification for all SKUs (rule-based v1 + optional v2 scoring)."""
    _ensure_sys_path()
    from services.lifecycle.config import LifecycleConfig
    from services.lifecycle.pipeline import build_summary, run_lifecycle_pipeline

    config = LifecycleConfig(db_path=DB_PATH)
    classifications, v2_scores = run_lifecycle_pipeline(
        config, include_v2_scoring=True, write_to_db=True,
    )

    if not classifications:
        context.log.warning("No SKUs classified — insufficient data")
        return Output(value={"status": "no_data", "classified": 0})

    summary = build_summary(classifications)
    context.log.info(
        f"Lifecycle: {summary.total_skus} SKUs classified, "
        f"stages: {summary.stage_counts}, avg confidence: {summary.avg_confidence:.2f}"
    )

    return Output(
        value={"status": "success", "classified": summary.total_skus},
        metadata={
            "total_skus": summary.total_skus,
            "avg_confidence": float(summary.avg_confidence),
            **{f"stage_{k}": v for k, v in summary.stage_counts.items()},
        },
    )


# ─── Optimization ────────────────────────────────────────────────────────────

@asset(group_name="optimization", deps=[demand_forecast, lifecycle_classification],
       description="Generate daily replenishment plan")
def replenishment_plan(context: AssetExecutionContext) -> Output:
    """Generate daily replenishment recommendations for all stores."""
    _ensure_sys_path()
    from services.replenishment.config import ReplenishmentConfig
    from services.replenishment.pipeline import run_replenishment_pipeline

    config = ReplenishmentConfig(db_path=DB_PATH)
    recommendations = run_replenishment_pipeline(config, write_to_db=True)

    n_recs = len(recommendations)
    n_stores = int(recommendations["destination_store"].nunique()) if not recommendations.empty else 0
    n_emergency = int((recommendations["urgency"] == "emergency").sum()) if not recommendations.empty else 0

    context.log.info(f"Replenishment: {n_recs} recommendations, "
                     f"{n_stores} stores, {n_emergency} emergency")

    return Output(
        value={"status": "success", "recommendations": n_recs},
        metadata={"n_recommendations": n_recs, "n_stores": n_stores, "n_emergency": n_emergency},
    )


@asset(group_name="optimization", deps=[demand_forecast, lifecycle_classification, store_clustering],
       description="Generate assortment plan")
def assortment_plan(context: AssetExecutionContext) -> Output:
    """Generate assortment optimization recommendations for all stores."""
    _ensure_sys_path()
    from services.assortment.config import AssortmentConfig
    from services.assortment.pipeline import run_assortment_pipeline

    config = AssortmentConfig(db_path=DB_PATH)
    results = run_assortment_pipeline(config, write_to_db=True)

    n_stores = len(results)
    n_optimal = sum(1 for r in results if r.status == "optimal")
    total_selected = sum(len(r.selected_skus) for r in results)
    total_obj = sum(r.objective_value for r in results)

    context.log.info(
        f"Assortment: {n_stores} stores optimized, "
        f"{n_optimal} optimal, {total_selected} SKUs selected"
    )

    return Output(
        value={"status": "success", "stores_optimized": n_stores},
        metadata={
            "n_stores": n_stores, "n_optimal": n_optimal,
            "total_selected": total_selected, "total_objective": float(total_obj),
        },
    )


@asset(group_name="optimization", deps=[demand_forecast, lifecycle_classification],
       description="Generate transfer plan")
def transfer_plan(context: AssetExecutionContext) -> Output:
    """Generate inter-store transfer recommendations."""
    _ensure_sys_path()
    from services.transfers.config import TransferConfig
    from services.transfers.pipeline import run_transfer_pipeline

    config = TransferConfig(db_path=DB_PATH)
    result = run_transfer_pipeline(config, write_to_db=True)

    context.log.info(
        f"Transfers: {result.selected_transfers} selected, "
        f"{result.total_units} units, net value ₹{result.net_value:,.0f}"
    )

    return Output(
        value={"status": result.status, "transfers": result.selected_transfers},
        metadata={
            "selected_transfers": result.selected_transfers,
            "total_units": result.total_units,
            "net_value": float(result.net_value),
        },
    )


# ─── Vendor Planning & PO ────────────────────────────────────────────────────

@asset(group_name="vendor", deps=[replenishment_plan], description="Generate PO suggestions")
def purchase_order_suggestions(context: AssetExecutionContext) -> Output:
    """Generate automated PO suggestions from replenishment needs and vendor scorecards."""
    _ensure_sys_path()
    from services.purchase_orders.config import PurchaseOrderConfig
    from services.purchase_orders.pipeline import run_po_pipeline

    config = PurchaseOrderConfig(db_path=DB_PATH)
    result = run_po_pipeline(config, write_to_db=True)

    context.log.info(
        f"POs: {result.total_pos} POs, {result.total_units} units, "
        f"₹{result.total_value:,.0f} value, {result.vendors_used} vendors"
    )

    return Output(
        value={"status": "success", "total_pos": result.total_pos},
        metadata={
            "total_pos": result.total_pos,
            "total_units": result.total_units,
            "total_value": float(result.total_value),
            "vendors_used": result.vendors_used,
            "skus_covered": result.skus_covered,
        },
    )
