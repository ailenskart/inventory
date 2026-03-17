"""Lifecycle Intelligence pipeline.

Orchestrates: data loading -> feature engineering -> classification -> output.

Usage:
    python -m services.lifecycle.pipeline
    python -m services.lifecycle.pipeline --sku SKU_001
    python -m services.lifecycle.pipeline --v2-scoring
"""

import argparse
import logging
import sys
from datetime import date, datetime

import duckdb
import pandas as pd

from schemas.lifecycle import LifecycleClassification, LifecycleSummary
from services.lifecycle.classifier import classify_skus
from services.lifecycle.config import LifecycleConfig
from services.lifecycle.features import compute_lifecycle_features
from services.lifecycle.scoring import compute_survival_scores

logger = logging.getLogger(__name__)


def run_lifecycle_pipeline(
    config: LifecycleConfig,
    sku_id: str | None = None,
    include_v2_scoring: bool = False,
    write_to_db: bool = True,
    output_path: str | None = None,
    as_of_date: date | None = None,
) -> tuple[list[LifecycleClassification], pd.DataFrame | None]:
    """Run the lifecycle intelligence pipeline.

    Args:
        config: Lifecycle configuration.
        sku_id: Classify a single SKU (None = all SKUs).
        include_v2_scoring: Also compute survival-analysis scores.
        write_to_db: Write results to DuckDB.
        output_path: Optional CSV output path.
        as_of_date: Reference date for feature computation.

    Returns:
        Tuple of (classifications, v2_scores_df or None).
    """
    logger.info("=" * 60)
    logger.info("Product Lifecycle Intelligence v1")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Step 1: Load data
    logger.info("Step 1: Loading data")
    sku_sales, sku_trials, sku_inventory, sku_master = _load_data(config, sku_id)

    if sku_sales.empty:
        logger.warning("No sales data available for lifecycle analysis")
        return [], None

    # Step 2: Compute features
    logger.info("Step 2: Computing lifecycle features")
    features_df = compute_lifecycle_features(
        sku_sales, sku_trials, sku_inventory, sku_master, config, as_of_date
    )

    if features_df.empty:
        logger.warning("No features computed — insufficient data")
        return [], None

    logger.info(f"Computed features for {len(features_df)} SKUs")

    # Step 3: Classify
    logger.info("Step 3: Running rule-based classification (v1)")
    classifications = classify_skus(features_df, config)

    # Step 4: Optional v2 scoring
    v2_scores = None
    if include_v2_scoring:
        logger.info("Step 4: Computing survival-analysis scores (v2)")
        v2_scores = compute_survival_scores(features_df, config)

    # Step 5: Write outputs
    if classifications:
        if write_to_db:
            _write_results_to_db(classifications, v2_scores, config)

        if output_path:
            _write_csv(classifications, v2_scores, output_path)

    _log_summary(classifications)
    return classifications, v2_scores


def _load_data(
    config: LifecycleConfig,
    sku_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load data from DuckDB for lifecycle analysis."""
    con = duckdb.connect(config.db_path, read_only=True)

    sku_filter = ""
    if sku_id:
        sku_filter = f"WHERE sku_id = '{sku_id}'"

    # Sales data
    try:
        sku_sales = con.execute(
            f"SELECT sku_id, sale_date, qty_sold FROM {config.sales_table} {sku_filter}"  # noqa: S608
        ).fetchdf()
    except Exception:
        logger.warning(f"Could not load sales from {config.sales_table}")
        sku_sales = pd.DataFrame()

    # Trial data
    try:
        sku_trials = con.execute(
            f"SELECT sku_id, trial_date, resulted_in_order FROM {config.trials_table} {sku_filter}"  # noqa: S608
        ).fetchdf()
    except Exception:
        logger.warning(f"Could not load trials from {config.trials_table}")
        sku_trials = pd.DataFrame()

    # Inventory data
    try:
        sku_inventory = con.execute(
            f"SELECT sku_id, on_hand_qty, snapshot_date FROM {config.inventory_table} {sku_filter}"  # noqa: S608
        ).fetchdf()
    except Exception:
        logger.warning(f"Could not load inventory from {config.inventory_table}")
        sku_inventory = pd.DataFrame()

    # SKU master
    try:
        sku_master = con.execute(
            f"SELECT sku_id, launch_date FROM {config.sku_table} {sku_filter}"  # noqa: S608
        ).fetchdf()
    except Exception:
        logger.warning(f"Could not load SKU master from {config.sku_table}")
        sku_master = pd.DataFrame()

    con.close()
    logger.info(
        f"Loaded: {len(sku_sales)} sales rows, {len(sku_trials)} trials, "
        f"{len(sku_inventory)} inventory snapshots, {len(sku_master)} SKU records"
    )
    return sku_sales, sku_trials, sku_inventory, sku_master


def _write_results_to_db(
    classifications: list[LifecycleClassification],
    v2_scores: pd.DataFrame | None,
    config: LifecycleConfig,
):
    """Write lifecycle results to DuckDB."""
    con = duckdb.connect(config.db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS main_ml")

    # Classifications
    records = []
    for c in classifications:
        records.append({
            "sku_id": c.sku_id,
            "lifecycle_stage": c.lifecycle_stage.value,
            "confidence": c.confidence,
            "recommended_action": c.recommended_action.value,
            "reason": c.reason,
            "classifier_version": c.classifier_version,
            "age_days": c.features.age_days,
            "sales_velocity_trend": c.features.sales_velocity_trend,
            "trial_trend": c.features.trial_trend,
            "conversion_trend": c.features.conversion_trend,
            "aging_inventory_pct": c.features.aging_inventory_pct,
            "avg_weekly_sales": c.features.avg_weekly_sales,
            "current_vs_peak_ratio": c.features.current_vs_peak_ratio,
            "classified_at": datetime.now(),
        })

    cls_df = pd.DataFrame(records)
    con.execute(f"DROP TABLE IF EXISTS {config.output_table}")  # noqa: S608
    con.execute(f"CREATE TABLE {config.output_table} AS SELECT * FROM cls_df")  # noqa: S608

    count = con.execute(f"SELECT count(*) FROM {config.output_table}").fetchone()[0]  # noqa: S608
    logger.info(f"Written {count} classifications to {config.output_table}")

    # V2 scores
    if v2_scores is not None and not v2_scores.empty:
        v2_table = f"{config.output_table}_v2_scores"
        con.execute(f"DROP TABLE IF EXISTS {v2_table}")  # noqa: S608
        con.execute(f"CREATE TABLE {v2_table} AS SELECT * FROM v2_scores")  # noqa: S608
        logger.info(f"Written v2 scores to {v2_table}")

    con.close()


def _write_csv(
    classifications: list[LifecycleClassification],
    v2_scores: pd.DataFrame | None,
    output_path: str,
):
    """Write results to CSV."""
    records = [
        {
            "sku_id": c.sku_id,
            "lifecycle_stage": c.lifecycle_stage.value,
            "confidence": c.confidence,
            "recommended_action": c.recommended_action.value,
            "reason": c.reason,
        }
        for c in classifications
    ]
    pd.DataFrame(records).to_csv(output_path, index=False)
    logger.info(f"Written classifications to {output_path}")


def _log_summary(classifications: list[LifecycleClassification]):
    """Log classification summary."""
    if not classifications:
        logger.info("No classifications to summarize")
        return

    summary = build_summary(classifications)

    logger.info("=" * 60)
    logger.info("Lifecycle Classification Summary")
    logger.info(f"  Total SKUs: {summary.total_skus}")
    logger.info(f"  Avg confidence: {summary.avg_confidence:.2f}")
    logger.info(f"  Stage distribution: {summary.stage_counts}")
    logger.info(f"  Action distribution: {summary.action_counts}")
    logger.info("=" * 60)


def build_summary(
    classifications: list[LifecycleClassification],
) -> LifecycleSummary:
    """Build aggregate summary from classifications."""
    stage_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    total_confidence = 0.0

    for c in classifications:
        stage = c.lifecycle_stage.value
        action = c.recommended_action.value
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
        total_confidence += c.confidence

    return LifecycleSummary(
        total_skus=len(classifications),
        stage_counts=stage_counts,
        action_counts=action_counts,
        avg_confidence=round(total_confidence / max(len(classifications), 1), 3),
    )


def main():
    parser = argparse.ArgumentParser(description="Run lifecycle intelligence pipeline")
    parser.add_argument("--db-path", default="data/dev.duckdb")
    parser.add_argument("--sku", type=str, default=None, help="Classify single SKU")
    parser.add_argument("--v2-scoring", action="store_true", help="Include survival scoring")
    parser.add_argument("--output", type=str, default=None, help="CSV output path")
    parser.add_argument("--no-db-write", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = LifecycleConfig(db_path=args.db_path)
    classifications, v2_scores = run_lifecycle_pipeline(
        config,
        sku_id=args.sku,
        include_v2_scoring=args.v2_scoring,
        write_to_db=not args.no_db_write,
        output_path=args.output,
    )

    if not classifications:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
