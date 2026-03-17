"""Training pipeline for demand forecasting.

Orchestrates the full training flow:
1. Load demand data from mart_demand_base
2. Apply stockout censoring
3. Generate features
4. Prepare StatsForecast input
5. Run cross-validation
6. Evaluate and select best model per series
7. Generate final forecasts
8. Apply hierarchical reconciliation
9. Log everything to MLflow

Usage:
    python -m ml.forecasting.train
    python -m ml.forecasting.train --horizon 8 --target sell_through_signal
"""

import argparse
import logging
import sys

import pandas as pd

from ml.forecasting.baseline import (
    create_ensemble_forecast,
    cross_validate,
    fit_and_forecast_with_quantiles,
    get_production_models,
    select_best_model,
)
from ml.forecasting.config import ForecastConfig
from ml.forecasting.data_loader import (
    apply_stockout_censoring,
    load_demand_data,
    prepare_statsforecast_df,
)
from ml.forecasting.evaluation import evaluate_forecasts, generate_evaluation_report
from ml.forecasting.hierarchy import build_hierarchy_tags, reconcile_forecasts

logger = logging.getLogger(__name__)


def run_training_pipeline(config: ForecastConfig) -> dict:
    """Execute the full training pipeline.

    Returns dict with forecasts, evaluation report, and model selection.
    """
    logger.info("=" * 60)
    logger.info("Demand Intelligence Engine v1 — Training Pipeline")
    logger.info("=" * 60)

    # Step 1: Load data
    logger.info("Step 1: Loading demand data")
    demand_df = load_demand_data(config)

    if demand_df.empty:
        logger.error("No demand data found. Run the data foundation pipeline first.")
        return {"status": "error", "message": "No demand data"}

    # Step 2: Stockout censoring
    logger.info("Step 2: Applying stockout censoring")
    demand_df = apply_stockout_censoring(demand_df, config)

    # Step 3: Prepare StatsForecast input
    logger.info("Step 3: Preparing forecast input")
    sf_df = prepare_statsforecast_df(demand_df, config)

    if sf_df.empty:
        logger.error("No series with sufficient history")
        return {"status": "error", "message": "Insufficient history"}

    # Step 4: Cross-validation
    logger.info("Step 4: Running cross-validation")
    models = get_production_models(config)
    cv_results = cross_validate(sf_df, config, models)

    # Step 5: Evaluate
    logger.info("Step 5: Evaluating models")
    model_columns = [c for c in cv_results.columns
                     if c not in ("unique_id", "ds", "y", "cutoff")]

    # Build dimension mapping for breakdowns
    dim_df = demand_df[["store_id", "sku_id", "store_cluster", "category",
                         "sku_type", "lifecycle_stage"]].drop_duplicates()
    dim_df["unique_id"] = dim_df["store_id"] + "__" + dim_df["sku_id"]

    report = generate_evaluation_report(cv_results, model_columns, dim_df)

    # Step 6: Model selection
    logger.info("Step 6: Selecting best model per series")
    selection = select_best_model(cv_results, model_columns)

    # Step 7: Generate final forecasts with quantiles
    logger.info("Step 7: Generating final forecasts")
    forecasts = fit_and_forecast_with_quantiles(sf_df, config, models)
    forecasts = create_ensemble_forecast(forecasts, model_columns)

    # Step 8: Hierarchical reconciliation
    logger.info("Step 8: Hierarchical reconciliation")
    try:
        agg_df, tags = build_hierarchy_tags(demand_df)
        # Reconcile bottom-level forecasts
        bottom_ids = set(tags.get("Bottom", []))
        bottom_forecasts = forecasts[forecasts["unique_id"].isin(bottom_ids)]
        if not bottom_forecasts.empty:
            reconciled = reconcile_forecasts(bottom_forecasts, tags, config.reconciliation_method)
            logger.info(f"Reconciled {len(reconciled)} hierarchical forecast rows")
    except Exception as e:
        logger.warning(f"Hierarchical reconciliation skipped: {e}")

    # Step 9: MLflow logging
    logger.info("Step 9: Logging to MLflow")
    try:
        from ml.forecasting.tracking import (
            end_run,
            init_tracking,
            log_evaluation_report,
            log_forecasts_artifact,
            log_model_selection,
            start_run,
        )

        init_tracking(config)
        start_run(config, run_name="train_v1")
        log_evaluation_report(report)
        log_model_selection(selection)
        log_forecasts_artifact(forecasts)
        end_run()
        logger.info("MLflow logging complete")
    except ImportError:
        logger.warning("MLflow not available, skipping tracking")
    except Exception as e:
        logger.warning(f"MLflow logging failed: {e}")

    # Add reason codes to forecasts
    forecasts = _add_reason_codes(forecasts, selection, demand_df)

    logger.info("=" * 60)
    logger.info("Training pipeline complete")
    logger.info(f"  Series: {forecasts['unique_id'].nunique()}")
    logger.info(f"  Forecast rows: {len(forecasts)}")
    if report.get("model_ranking"):
        best = report["model_ranking"][0]
        logger.info(f"  Best model: {best['model']} (WMAPE={best.get('wmape', 'N/A'):.4f})")
    logger.info("=" * 60)

    return {
        "status": "success",
        "forecasts": forecasts,
        "cv_results": cv_results,
        "report": report,
        "selection": selection,
    }


def _add_reason_codes(
    forecasts: pd.DataFrame,
    selection: pd.DataFrame,
    demand_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add human-readable reason codes to forecasts."""
    forecasts = forecasts.merge(
        selection[["unique_id", "best_model", "best_wmape"]],
        on="unique_id",
        how="left",
    )

    # Add SKU type context
    sku_map = demand_df[["store_id", "sku_id", "sku_type", "fulfillment_type",
                          "category", "is_display_only"]].drop_duplicates()
    sku_map["unique_id"] = sku_map["store_id"] + "__" + sku_map["sku_id"]

    forecasts = forecasts.merge(
        sku_map[["unique_id", "sku_type", "fulfillment_type", "category", "is_display_only"]],
        on="unique_id",
        how="left",
    )

    # Reason code
    conditions = []
    forecasts["reason_code"] = "standard_forecast"

    if "is_display_only" in forecasts.columns:
        mask = forecasts["is_display_only"] == 1
        forecasts.loc[mask, "reason_code"] = "display_only_trial_demand"

    if "best_wmape" in forecasts.columns:
        mask = forecasts["best_wmape"] > 0.5
        forecasts.loc[mask, "reason_code"] = forecasts.loc[mask, "reason_code"] + "|high_uncertainty"

    return forecasts


def main():
    parser = argparse.ArgumentParser(description="Train demand forecasting models")
    parser.add_argument("--db-path", default="data/dev.duckdb", help="Path to DuckDB database")
    parser.add_argument("--horizon", type=int, default=4, help="Forecast horizon in weeks")
    parser.add_argument("--target", default="total_qty_sold", help="Target column to forecast")
    parser.add_argument("--no-stockout-censoring", action="store_true", help="Disable stockout censoring")
    parser.add_argument("--reconciliation", default="MinTrace", choices=["MinTrace", "BottomUp", "TopDown"])
    parser.add_argument("--min-history", type=int, default=12, help="Minimum weeks of history per series")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = ForecastConfig(
        db_path=args.db_path,
        horizon_weeks=args.horizon,
        target_column=args.target,
        censor_stockout_demand=not args.no_stockout_censoring,
        reconciliation_method=args.reconciliation,
        min_history_weeks=args.min_history,
    )

    result = run_training_pipeline(config)

    if result["status"] == "success":
        logger.info("Training completed successfully")
        sys.exit(0)
    else:
        logger.error(f"Training failed: {result.get('message')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
