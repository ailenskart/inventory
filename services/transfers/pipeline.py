"""Transfer optimization pipeline — orchestrates data loading, optimization, and output.

Usage:
    python -m services.transfers.pipeline
    python -m services.transfers.pipeline --db-path data/dev.duckdb --output data/transfers.csv
"""

import argparse
import logging
import sys
from datetime import datetime

import pandas as pd

from services.transfers.config import TransferConfig
from services.transfers.data_loader import (
    build_transfer_inputs,
    write_transfer_recommendations,
)
from services.transfers.engine import (
    TransferResult,
    generate_candidates,
    optimize_transfers,
)

logger = logging.getLogger(__name__)


def run_transfer_pipeline(
    config: TransferConfig,
    output_path: str | None = None,
    write_to_db: bool = True,
) -> TransferResult:
    """Run the full inter-store transfer optimization pipeline.

    1. Load inventory positions, forecasts, store metadata
    2. Generate transfer candidates
    3. Optimize transfer selection
    4. Write results to DB and/or CSV

    Returns:
        TransferResult with selected transfers and metrics
    """
    logger.info("=" * 60)
    logger.info("Inter-Store Transfer Optimizer v1")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info(f"Frequency: {config.run_frequency}")
    logger.info("=" * 60)

    # Step 1: Build inputs
    logger.info("Step 1: Loading data and building transfer inputs")
    positions = build_transfer_inputs(config)
    if positions.empty:
        logger.warning("No eligible positions — exiting")
        return TransferResult(
            status="no_data", solve_time_ms=0,
            total_candidates=0, selected_transfers=0,
            total_units=0, total_recovered_value=0,
            total_transfer_cost=0, net_value=0,
        )

    # Step 2: Generate candidates
    logger.info("Step 2: Generating transfer candidates")
    candidates = generate_candidates(positions, config)
    if candidates.empty:
        logger.info("No viable transfer candidates found")
        return TransferResult(
            status="no_candidates", solve_time_ms=0,
            total_candidates=0, selected_transfers=0,
            total_units=0, total_recovered_value=0,
            total_transfer_cost=0, net_value=0,
        )

    # Step 3: Optimize
    logger.info("Step 3: Running transfer optimization")
    result = optimize_transfers(candidates, config)

    # Step 4: Write outputs
    if result.transfers:
        rec_df = pd.DataFrame(result.transfers)
        rec_df["run_date"] = datetime.now().date()
        rec_df["run_timestamp"] = datetime.now().isoformat()

        if write_to_db:
            logger.info("Step 4: Writing to database")
            write_transfer_recommendations(rec_df, config)

        if output_path:
            rec_df.to_csv(output_path, index=False)
            logger.info(f"Written to {output_path}")

    # Summary
    _log_summary(result)

    return result


def _log_summary(result: TransferResult):
    """Log transfer optimization summary."""
    logger.info("=" * 60)
    logger.info("Transfer Optimization Summary")
    logger.info(f"  Status: {result.status}")
    logger.info(f"  Candidates evaluated: {result.total_candidates}")
    logger.info(f"  Transfers selected: {result.selected_transfers}")
    logger.info(f"  Total units to transfer: {result.total_units}")
    logger.info(f"  Recovered sales value: ₹{result.total_recovered_value:,.0f}")
    logger.info(f"  Transfer cost: ₹{result.total_transfer_cost:,.0f}")
    logger.info(f"  Net value: ₹{result.net_value:,.0f}")
    logger.info(f"  Solve time: {result.solve_time_ms:.0f}ms")

    if result.source_relief:
        logger.info(f"  Source stores relieved: {len(result.source_relief)}")
        total_aging = sum(s["aging_cleared"] for s in result.source_relief.values())
        if total_aging > 0:
            logger.info(f"  Aging/EOL units cleared: {total_aging}")

    if result.diagnostics:
        diag = result.diagnostics
        if "reason_breakdown" in diag:
            logger.info("  Reason breakdown:")
            for reason, count in diag["reason_breakdown"].items():
                logger.info(f"    {reason}: {count}")

    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Run inter-store transfer optimization"
    )
    parser.add_argument("--db-path", default="data/dev.duckdb")
    parser.add_argument("--output", type=str, default=None, help="CSV output path")
    parser.add_argument("--no-db-write", action="store_true")
    parser.add_argument(
        "--frequency", choices=["daily", "weekly"], default="weekly",
        help="Run frequency hint",
    )
    parser.add_argument(
        "--min-source-wos", type=float, default=8.0,
        help="Minimum weeks-of-supply at source",
    )
    parser.add_argument(
        "--max-dest-wos", type=float, default=3.0,
        help="Maximum weeks-of-supply at destination",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = TransferConfig(
        db_path=args.db_path,
        run_frequency=args.frequency,
        min_source_wos=args.min_source_wos,
        max_destination_wos=args.max_dest_wos,
    )

    result = run_transfer_pipeline(
        config,
        output_path=args.output,
        write_to_db=not args.no_db_write,
    )

    if not result.transfers:
        logger.info("No transfers recommended")
        sys.exit(0)

    logger.info(f"Pipeline complete: {result.selected_transfers} transfers recommended")
    sys.exit(0)


if __name__ == "__main__":
    main()
