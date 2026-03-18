#!/usr/bin/env python3
"""End-to-end demo of the Lenskart Retail Intelligence Platform.

Runs the full pipeline using synthetic data:
1. Data foundation (generate → seed → transform)
2. Demand forecasting (train → predict)
3. Lifecycle classification
4. Replenishment planning
5. Assortment optimization
6. Transfer optimization
7. PO recommendation
8. Control tower summary

Usage:
    python scripts/demo_e2e.py
    python scripts/demo_e2e.py --skip-data-foundation  # Skip if already loaded
    python scripts/demo_e2e.py --api-only               # Just start the API
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time

# Ensure project root is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("demo")

DB_PATH = os.path.join(PROJECT_ROOT, "data", "dev.duckdb")
DBT_DIR = os.path.join(PROJECT_ROOT, "transform", "dbt")


def run_cmd(cmd: list[str], cwd: str = PROJECT_ROOT, label: str = "") -> bool:
    """Run a command with logging."""
    logger.info(f"{'─' * 60}")
    logger.info(f"Running: {label or ' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.error(f"FAILED: {result.stderr[:500]}")
        return False
    logger.info(f"OK: {label or cmd[0]}")
    return True


def step_data_foundation() -> bool:
    """Generate synthetic data and run dbt pipeline."""
    logger.info("=" * 60)
    logger.info("STEP 1: DATA FOUNDATION")
    logger.info("=" * 60)

    steps = [
        ([sys.executable, "data/synthetic/generate.py"], PROJECT_ROOT, "Generate synthetic data"),
        ([sys.executable, "data/load_seeds.py"], PROJECT_ROOT, "Copy CSVs to dbt seeds"),
        (["dbt", "seed", "--profiles-dir", ".", "--full-refresh"], DBT_DIR, "dbt seed"),
        (["dbt", "run", "--profiles-dir", "."], DBT_DIR, "dbt run (staging → dims → marts)"),
        (["dbt", "test", "--profiles-dir", "."], DBT_DIR, "dbt test"),
        ([sys.executable, "data/validate.py"], PROJECT_ROOT, "Data validation"),
    ]

    for cmd, cwd, label in steps:
        if not run_cmd(cmd, cwd, label):
            return False
    return True


def step_forecasting() -> bool:
    """Train models and generate forecasts."""
    logger.info("=" * 60)
    logger.info("STEP 2: DEMAND FORECASTING")
    logger.info("=" * 60)

    from ml.forecasting.config import ForecastConfig
    from ml.forecasting.predict import run_inference_pipeline
    from ml.forecasting.train import run_training_pipeline

    config = ForecastConfig(db_path=DB_PATH)

    logger.info("Training models...")
    result = run_training_pipeline(config)
    report = result.get("report", {})
    if report.get("model_ranking"):
        best = report["model_ranking"][0]
        logger.info(f"Best model: {best['model']} (WMAPE: {best.get('wmape', 'N/A')})")

    logger.info("Running batch inference...")
    forecasts = run_inference_pipeline(config, write_to_db=True)
    if forecasts.empty:
        logger.warning("No forecasts generated")
        return False

    logger.info(f"Generated {len(forecasts)} forecasts for "
                f"{forecasts['store_id'].nunique()} stores, "
                f"{forecasts['sku_id'].nunique()} SKUs")
    return True


def step_lifecycle() -> bool:
    """Run lifecycle classification."""
    logger.info("=" * 60)
    logger.info("STEP 3: LIFECYCLE INTELLIGENCE")
    logger.info("=" * 60)

    from services.lifecycle.config import LifecycleConfig
    from services.lifecycle.pipeline import build_summary, run_lifecycle_pipeline

    config = LifecycleConfig(db_path=DB_PATH)
    classifications, v2_scores = run_lifecycle_pipeline(
        config, include_v2_scoring=True, write_to_db=True,
    )

    if not classifications:
        logger.warning("No SKUs classified")
        return True  # Non-fatal

    summary = build_summary(classifications)
    logger.info(f"Classified {summary.total_skus} SKUs")
    logger.info(f"Stage distribution: {summary.stage_counts}")
    logger.info(f"Action distribution: {summary.action_counts}")
    logger.info(f"Avg confidence: {summary.avg_confidence:.2f}")
    return True


def step_replenishment() -> bool:
    """Run replenishment pipeline."""
    logger.info("=" * 60)
    logger.info("STEP 4: REPLENISHMENT")
    logger.info("=" * 60)

    from services.replenishment.config import ReplenishmentConfig
    from services.replenishment.pipeline import run_replenishment_pipeline

    config = ReplenishmentConfig(db_path=DB_PATH)
    recs = run_replenishment_pipeline(config, write_to_db=True)

    if recs.empty:
        logger.info("No replenishment needed")
        return True

    logger.info(f"Generated {len(recs)} recommendations for "
                f"{recs['destination_store'].nunique()} stores")
    logger.info(f"Emergency: {(recs['urgency'] == 'emergency').sum()}, "
                f"Urgent: {(recs['urgency'] == 'urgent').sum()}")
    return True


def step_assortment() -> bool:
    """Run assortment optimization."""
    logger.info("=" * 60)
    logger.info("STEP 5: ASSORTMENT OPTIMIZATION")
    logger.info("=" * 60)

    from services.assortment.config import AssortmentConfig
    from services.assortment.pipeline import run_assortment_pipeline

    config = AssortmentConfig(db_path=DB_PATH)
    results = run_assortment_pipeline(config, write_to_db=True)

    if not results:
        logger.info("No assortment results")
        return True

    optimal = sum(1 for r in results if r.status == "optimal")
    total_selected = sum(len(r.selected_skus) for r in results)
    logger.info(f"Optimized {len(results)} stores ({optimal} optimal), "
                f"{total_selected} SKUs selected")
    return True


def step_transfers() -> bool:
    """Run transfer optimization."""
    logger.info("=" * 60)
    logger.info("STEP 6: TRANSFER OPTIMIZATION")
    logger.info("=" * 60)

    from services.transfers.config import TransferConfig
    from services.transfers.pipeline import run_transfer_pipeline

    config = TransferConfig(db_path=DB_PATH)
    result = run_transfer_pipeline(config, write_to_db=True)

    logger.info(f"Status: {result.status}, "
                f"{result.selected_transfers} transfers, "
                f"{result.total_units} units, "
                f"net value: ₹{result.net_value:,.0f}")
    return True


def step_purchase_orders() -> bool:
    """Run PO recommendation pipeline."""
    logger.info("=" * 60)
    logger.info("STEP 7: PURCHASE ORDER RECOMMENDATIONS")
    logger.info("=" * 60)

    from services.purchase_orders.config import PurchaseOrderConfig
    from services.purchase_orders.pipeline import run_po_pipeline

    config = PurchaseOrderConfig(db_path=DB_PATH)
    result = run_po_pipeline(config, write_to_db=True)

    logger.info(f"Generated {result.total_pos} POs, "
                f"{result.total_units} units, "
                f"₹{result.total_value:,.0f} value, "
                f"{result.vendors_used} vendors")
    return True


def step_control_tower() -> bool:
    """Print control tower summary."""
    logger.info("=" * 60)
    logger.info("STEP 8: CONTROL TOWER SUMMARY")
    logger.info("=" * 60)

    import duckdb

    con = duckdb.connect(DB_PATH, read_only=True)
    summary = {}

    # Forecasts
    try:
        row = con.execute("SELECT count(*), count(DISTINCT store_id), count(DISTINCT sku_id) FROM main_ml.demand_forecasts").fetchone()
        summary["forecasts"] = {"rows": row[0], "stores": row[1], "skus": row[2]}
    except Exception:
        summary["forecasts"] = "not available"

    # Inventory health
    try:
        rows = con.execute("SELECT inventory_status, count(*) FROM main_marts.mart_inventory_position GROUP BY 1").fetchall()
        summary["inventory_health"] = {r[0]: r[1] for r in rows}
    except Exception:
        summary["inventory_health"] = "not available"

    # Replenishment
    try:
        row = con.execute("SELECT count(*), sum(recommended_qty) FROM main_ml.replenishment_recommendations").fetchone()
        summary["replenishment"] = {"recommendations": row[0], "total_units": int(row[1] or 0)}
    except Exception:
        summary["replenishment"] = "not available"

    # Transfers
    try:
        row = con.execute("SELECT count(*), sum(qty), sum(net_value) FROM main_ml.transfer_recommendations").fetchone()
        summary["transfers"] = {"count": row[0], "units": int(row[1] or 0), "net_value": float(row[2] or 0)}
    except Exception:
        summary["transfers"] = "not available"

    # POs
    try:
        row = con.execute("SELECT count(DISTINCT po_id), sum(qty_ordered), sum(line_value) FROM main_ml.po_recommendations").fetchone()
        summary["purchase_orders"] = {"pos": row[0], "units": int(row[1] or 0), "value": float(row[2] or 0)}
    except Exception:
        summary["purchase_orders"] = "not available"

    # Lifecycle
    try:
        rows = con.execute("SELECT lifecycle_stage, count(*) FROM main_ml.lifecycle_classifications GROUP BY 1").fetchall()
        summary["lifecycle"] = {r[0]: r[1] for r in rows}
    except Exception:
        summary["lifecycle"] = "not available"

    con.close()

    logger.info("\n" + json.dumps(summary, indent=2, default=str))
    logger.info("=" * 60)
    logger.info("DEMO COMPLETE")
    logger.info("=" * 60)
    logger.info("Start the API server with: make api")
    logger.info("Visit http://localhost:8000/docs for Swagger UI")
    logger.info("Control tower: GET /api/v1/control-tower/summary")
    return True


def main():
    parser = argparse.ArgumentParser(description="End-to-end demo")
    parser.add_argument("--skip-data-foundation", action="store_true",
                        help="Skip data generation and dbt pipeline")
    parser.add_argument("--api-only", action="store_true",
                        help="Just start the API server")
    args = parser.parse_args()

    if args.api_only:
        os.execvp("uvicorn", ["uvicorn", "apps.api.app.main:app",
                               "--reload", "--host", "0.0.0.0", "--port", "8000"])
        return

    start = time.time()

    if not args.skip_data_foundation:
        if not step_data_foundation():
            logger.error("Data foundation failed — aborting")
            sys.exit(1)

    steps = [
        ("Forecasting", step_forecasting),
        ("Lifecycle", step_lifecycle),
        ("Replenishment", step_replenishment),
        ("Assortment", step_assortment),
        ("Transfers", step_transfers),
        ("Purchase Orders", step_purchase_orders),
        ("Control Tower", step_control_tower),
    ]

    for name, func in steps:
        try:
            if not func():
                logger.error(f"{name} step failed")
        except Exception as e:
            logger.error(f"{name} step error: {e}")

    elapsed = time.time() - start
    logger.info(f"\nTotal demo time: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
