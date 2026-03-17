"""Assortment optimization pipeline.

Orchestrates: data loading → scoring → optimization → output.

Usage:
    python -m services.assortment.pipeline
    python -m services.assortment.pipeline --store STORE_001 --scenario metro_premium
"""

import argparse
import logging
import sys
from datetime import datetime

import duckdb
import pandas as pd

from services.assortment.config import (
    SCENARIOS,
    AssortmentConfig,
    get_scenario_for_cluster,
)
from services.assortment.data_loader import build_optimization_input
from services.assortment.optimizer import OptimizationResult, optimize_store_assortment
from services.assortment.scoring import compute_sku_scores

logger = logging.getLogger(__name__)


def run_assortment_pipeline(
    config: AssortmentConfig,
    store_id: str | None = None,
    scenario_override: str | None = None,
    write_to_db: bool = True,
    output_path: str | None = None,
) -> list[OptimizationResult]:
    """Run assortment optimization for one or all stores.

    Args:
        config: Global configuration
        store_id: Optimize for a single store (None = all stores)
        scenario_override: Force a specific scenario for all stores
        write_to_db: Write results to DuckDB
        output_path: Optional CSV output path

    Returns:
        List of OptimizationResult per store
    """
    logger.info("=" * 60)
    logger.info("Assortment Optimization Engine v1")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Step 1: Load data
    logger.info("Step 1: Loading optimization input")
    sku_data, stores = build_optimization_input(config, store_id)
    if sku_data.empty or stores.empty:
        logger.warning("No data available for optimization")
        return []

    # Step 2: Optimize per store
    results = []
    for _, store_row in stores.iterrows():
        sid = store_row["store_id"]
        cluster = store_row.get("store_cluster", "METRO_MID")
        capacity = int(store_row.get("display_capacity", 100))

        # Get scenario
        if scenario_override and scenario_override in SCENARIOS:
            scenario = SCENARIOS[scenario_override]
        else:
            scenario = get_scenario_for_cluster(cluster)

        # Filter SKU data for this store
        store_skus = sku_data[sku_data["store_id"] == sid].copy()
        if store_skus.empty:
            logger.info(f"Store {sid}: no candidate SKUs, skipping")
            continue

        # Score SKUs
        scored = compute_sku_scores(store_skus, scenario, config)

        # Optimize
        result = optimize_store_assortment(
            store_id=sid,
            sku_data=scored,
            display_capacity=capacity,
            scenario=scenario,
            config=config,
        )
        results.append(result)

    # Step 3: Write outputs
    if results:
        all_selected = []
        all_excluded = []
        for r in results:
            all_selected.extend(r.selected_skus)
            all_excluded.extend(r.excluded_skus)

        if write_to_db and all_selected:
            _write_results_to_db(all_selected, all_excluded, config)

        if output_path and all_selected:
            pd.DataFrame(all_selected).to_csv(output_path, index=False)
            logger.info(f"Written to {output_path}")

    _log_summary(results)
    return results


def _write_results_to_db(
    selected: list[dict],
    excluded: list[dict],
    config: AssortmentConfig,
):
    """Write assortment results to DuckDB."""
    con = duckdb.connect(config.db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS main_ml")

    # Selected assortment
    selected_df = pd.DataFrame(selected)
    selected_df["run_date"] = datetime.now().date()
    con.execute(f"DROP TABLE IF EXISTS {config.output_table}")  # noqa: S608
    con.execute(f"CREATE TABLE {config.output_table} AS SELECT * FROM selected_df")  # noqa: S608

    count = con.execute(f"SELECT count(*) FROM {config.output_table}").fetchone()[0]  # noqa: S608
    con.close()
    logger.info(f"Written {count} assortment selections to {config.output_table}")


def _log_summary(results: list[OptimizationResult]):
    """Log optimization summary."""
    if not results:
        logger.info("No results to summarize")
        return

    logger.info("=" * 60)
    logger.info("Assortment Optimization Summary")
    logger.info(f"  Stores optimized: {len(results)}")

    optimal = sum(1 for r in results if r.status == "optimal")
    feasible = sum(1 for r in results if r.status == "feasible")
    infeasible = sum(1 for r in results if r.status == "infeasible")
    logger.info(f"  Optimal: {optimal}, Feasible: {feasible}, Infeasible: {infeasible}")

    total_selected = sum(len(r.selected_skus) for r in results)
    total_capacity = sum(r.total_capacity for r in results)
    logger.info(f"  Total SKUs selected: {total_selected} / {total_capacity} capacity")

    avg_util = sum(r.used_capacity / max(r.total_capacity, 1) for r in results) / max(len(results), 1)
    logger.info(f"  Avg capacity utilization: {avg_util:.1%}")

    avg_time = sum(r.solve_time_ms for r in results) / max(len(results), 1)
    logger.info(f"  Avg solve time: {avg_time:.0f}ms")

    total_obj = sum(r.objective_value for r in results)
    logger.info(f"  Total objective value: {total_obj:,.0f}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run assortment optimization")
    parser.add_argument("--db-path", default="data/dev.duckdb")
    parser.add_argument("--store", type=str, default=None, help="Optimize single store")
    parser.add_argument("--scenario", type=str, default=None,
                        choices=list(SCENARIOS.keys()),
                        help="Force scenario for all stores")
    parser.add_argument("--output", type=str, default=None, help="CSV output path")
    parser.add_argument("--no-db-write", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = AssortmentConfig(db_path=args.db_path)
    results = run_assortment_pipeline(
        config,
        store_id=args.store,
        scenario_override=args.scenario,
        write_to_db=not args.no_db_write,
        output_path=args.output,
    )

    if not results:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
