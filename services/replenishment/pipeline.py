"""Replenishment pipeline — orchestrates data loading, engine, and output.

Usage:
    python -m services.replenishment.pipeline
    python -m services.replenishment.pipeline --db-path data/dev.duckdb --output data/replenishment.csv
"""

import argparse
import logging
import sys
from datetime import datetime

import pandas as pd

from services.replenishment.config import ReplenishmentConfig
from services.replenishment.data_loader import (
    build_replenishment_positions,
    write_recommendations_to_db,
)
from services.replenishment.engine import generate_recommendations

logger = logging.getLogger(__name__)


def run_replenishment_pipeline(
    config: ReplenishmentConfig,
    output_path: str | None = None,
    write_to_db: bool = True,
) -> pd.DataFrame:
    """Run the full replenishment pipeline.

    1. Load inventory positions + forecasts + constraints
    2. Run replenishment engine
    3. Write results to DB and/or CSV

    Returns:
        DataFrame of replenishment recommendations
    """
    logger.info("=" * 60)
    logger.info("Replenishment Engine v1 — Daily Run")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Step 1: Build positions
    logger.info("Step 1: Loading data and building positions")
    positions = build_replenishment_positions(config)
    if positions.empty:
        logger.warning("No positions found — exiting")
        return pd.DataFrame()

    # Step 2: Generate recommendations
    logger.info("Step 2: Running replenishment engine")
    recommendations = generate_recommendations(positions, config)

    # Step 3: Add metadata
    recommendations["run_date"] = datetime.now().date()
    recommendations["run_timestamp"] = datetime.now().isoformat()

    # Step 4: Write outputs
    if write_to_db:
        logger.info("Step 3: Writing to database")
        write_recommendations_to_db(recommendations, config)

    if output_path:
        recommendations.to_csv(output_path, index=False)
        logger.info(f"Written to {output_path}")

    # Summary
    _log_summary(recommendations, positions)

    return recommendations


def _log_summary(recommendations: pd.DataFrame, positions: pd.DataFrame):
    """Log replenishment summary statistics."""
    total_positions = len(positions)
    total_recs = len(recommendations)

    logger.info("=" * 60)
    logger.info("Replenishment Summary")
    logger.info(f"  Total positions evaluated: {total_positions}")
    logger.info(f"  Recommendations generated: {total_recs}")

    if not recommendations.empty:
        logger.info(f"  Stores affected: {recommendations['destination_store'].nunique()}")
        logger.info(f"  SKUs to replenish: {recommendations['sku_id'].nunique()}")
        logger.info(f"  Total units recommended: {recommendations['recommended_qty'].sum():,.0f}")

        urgency_counts = recommendations["urgency"].value_counts()
        for urgency, count in urgency_counts.items():
            logger.info(f"  {urgency}: {count} recommendations")

        reason_counts = recommendations["reason_code"].value_counts()
        logger.info("  Reason breakdown:")
        for reason, count in reason_counts.items():
            logger.info(f"    {reason}: {count}")

        avg_doc = recommendations["expected_days_of_cover_after"].replace(
            float("inf"), pd.NA
        ).mean()
        logger.info(f"  Avg days-of-cover after replenishment: {avg_doc:.1f}")

        total_lost_sales = recommendations["lost_sales_estimate"].sum()
        if total_lost_sales > 0:
            logger.info(f"  Total lost-sales at risk: ₹{total_lost_sales:,.0f}")

    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run daily replenishment pipeline")
    parser.add_argument("--db-path", default="data/dev.duckdb")
    parser.add_argument("--output", type=str, default=None, help="CSV output path")
    parser.add_argument("--no-db-write", action="store_true")
    parser.add_argument("--target-doc", type=int, default=28, help="Target days of cover")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = ReplenishmentConfig(
        db_path=args.db_path,
        target_days_of_cover=args.target_doc,
    )

    result = run_replenishment_pipeline(
        config,
        output_path=args.output,
        write_to_db=not args.no_db_write,
    )

    if result.empty:
        logger.warning("No recommendations generated")
        sys.exit(0)

    logger.info(f"Pipeline complete: {len(result)} recommendations")
    sys.exit(0)


if __name__ == "__main__":
    main()
