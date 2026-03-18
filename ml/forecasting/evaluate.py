"""Standalone evaluation script for forecast quality assessment.

Runs cross-validation and generates a comprehensive evaluation report
with breakdowns by store cluster, category, SKU type, and lifecycle stage.

Usage:
    python -m ml.forecasting.evaluate
    python -m ml.forecasting.evaluate --output data/eval_report.json
"""

import argparse
import json
import logging
import sys

import pandas as pd

from ml.forecasting.baseline import cross_validate, get_production_models
from ml.forecasting.config import ForecastConfig
from ml.forecasting.data_loader import (
    apply_stockout_censoring,
    load_demand_data,
    prepare_statsforecast_df,
)
from ml.forecasting.evaluation import (
    evaluate_forecasts,
    evaluate_per_series,
    generate_evaluation_report,
)

logger = logging.getLogger(__name__)


def run_evaluation(config: ForecastConfig, output_path: str | None = None) -> dict:
    """Run full evaluation pipeline.

    Returns:
        Evaluation report dict with aggregate, per-series, and dimensional metrics.
    """
    logger.info("=" * 60)
    logger.info("Demand Intelligence Engine v1 — Evaluation")
    logger.info("=" * 60)

    # Load data
    demand_df = load_demand_data(config)
    if demand_df.empty:
        return {"status": "error", "message": "No data"}

    demand_df = apply_stockout_censoring(demand_df, config)
    sf_df = prepare_statsforecast_df(demand_df, config)

    # Cross-validate
    models = get_production_models(config)
    cv_results = cross_validate(sf_df, config, models)

    model_columns = [c for c in cv_results.columns
                     if c not in ("unique_id", "ds", "y", "cutoff")]

    # Build dimension mapping
    dim_df = demand_df[["store_id", "sku_id", "store_cluster", "category",
                         "sku_type", "lifecycle_stage"]].drop_duplicates()
    dim_df["unique_id"] = dim_df["store_id"] + "__" + dim_df["sku_id"]

    # Generate report
    report = generate_evaluation_report(cv_results, model_columns, dim_df)

    # Per-series evaluation for best model
    if report.get("model_ranking"):
        best_model = report["model_ranking"][0]["model"]
        per_series = evaluate_per_series(cv_results, best_model)
        report["per_series_summary"] = {
            "total_series": len(per_series),
            "median_wmape": float(per_series["wmape"].median()),
            "p90_wmape": float(per_series["wmape"].quantile(0.9)),
            "pct_under_30pct_wmape": float((per_series["wmape"] < 0.3).mean()),
        }

    # In-stock-only vs censored-demand comparison
    if "had_stockout" in demand_df.columns:
        in_stock = demand_df[demand_df["had_stockout"] == 0]
        sf_instock = prepare_statsforecast_df(in_stock, config)
        if not sf_instock.empty:
            cv_instock = cross_validate(sf_instock, config, models)
            if report.get("model_ranking"):
                best_model = report["model_ranking"][0]["model"]
                if best_model in cv_instock.columns:
                    instock_metrics = evaluate_forecasts(cv_instock, best_model)
                    report["in_stock_only_metrics"] = instock_metrics

    # Print summary
    logger.info("\n--- Model Ranking ---")
    for rank in report.get("model_ranking", []):
        logger.info(f"  {rank['model']}: WMAPE={rank.get('wmape', 'N/A'):.4f}, "
                     f"Bias={rank.get('bias', 'N/A'):.4f}")

    if "per_series_summary" in report:
        s = report["per_series_summary"]
        logger.info(f"\n--- Per-Series Summary ---")
        logger.info(f"  Median WMAPE: {s['median_wmape']:.4f}")
        logger.info(f"  P90 WMAPE: {s['p90_wmape']:.4f}")
        logger.info(f"  % series < 30% WMAPE: {s['pct_under_30pct_wmape']:.1%}")

    # Save report
    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"Report saved to {output_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Evaluate forecast model quality")
    parser.add_argument("--db-path", default="data/dev.duckdb")
    parser.add_argument("--target", default="total_qty_sold")
    parser.add_argument("--output", default=None)
    parser.add_argument("--min-history", type=int, default=12)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = ForecastConfig(
        db_path=args.db_path,
        target_column=args.target,
        min_history_weeks=args.min_history,
    )

    report = run_evaluation(config, args.output)
    if report.get("status") == "error":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
