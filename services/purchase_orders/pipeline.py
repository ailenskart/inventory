"""PO recommendation pipeline — orchestrates data loading, recommendation, and output.

Usage:
    python -m services.purchase_orders.pipeline
    python -m services.purchase_orders.pipeline --db-path data/dev.duckdb --output data/po_recommendations.csv
"""

import argparse
import logging
import sys
from datetime import date, datetime

import duckdb
import pandas as pd

from services.purchase_orders.config import PurchaseOrderConfig
from services.purchase_orders.recommendation_engine import (
    PORecommendationResult,
    generate_po_recommendations,
)

logger = logging.getLogger(__name__)


def load_replenishment_needs(config: PurchaseOrderConfig) -> pd.DataFrame:
    """Load replenishment recommendations that need POs."""
    con = duckdb.connect(config.db_path, read_only=True)
    try:
        con.execute(f"SELECT 1 FROM {config.replenishment_table} LIMIT 1")  # noqa: S608
    except Exception:
        con.close()
        logger.warning(f"Replenishment table {config.replenishment_table} not found")
        return pd.DataFrame()

    query = f"""
        SELECT
            sku_id, destination_store, source_location,
            recommended_qty, urgency, reason_code,
            category, sku_type, vendor_id,
            lead_time_days, lost_sales_estimate
        FROM {config.replenishment_table}
        WHERE recommended_qty > 0
        ORDER BY urgency_rank, lost_sales_estimate DESC
    """  # noqa: S608
    df = con.execute(query).fetchdf()
    con.close()
    logger.info(f"Loaded {len(df)} replenishment needs")
    return df


def load_vendor_performance(config: PurchaseOrderConfig) -> pd.DataFrame:
    """Load vendor performance data for scorecards."""
    con = duckdb.connect(config.db_path, read_only=True)

    # Try mart_vendor_performance first, fall back to dim_vendor
    try:
        con.execute(f"SELECT 1 FROM {config.vendor_performance_table} LIMIT 1")  # noqa: S608
        query = f"SELECT * FROM {config.vendor_performance_table}"  # noqa: S608
    except Exception:
        logger.info("Vendor performance mart not available, using dim_vendor")
        query = f"""
            SELECT
                vendor_id, vendor_name, vendor_type,
                avg_lead_time_days, min_order_value, min_order_qty,
                reliability_score, is_active,
                0 as total_pos, 0 as received_pos,
                0 as total_units_ordered, 0 as total_po_value,
                0.0 as avg_delivery_delay_days,
                0 as late_deliveries, 0 as on_time_deliveries,
                0 as total_skus, 0 as active_skus
            FROM {config.vendor_dim_table}
            WHERE is_active = true
        """  # noqa: S608

    df = con.execute(query).fetchdf()
    con.close()
    logger.info(f"Loaded performance data for {len(df)} vendors")
    return df


def write_po_recommendations(
    result: PORecommendationResult,
    config: PurchaseOrderConfig,
):
    """Write PO recommendations to DuckDB."""
    if not result.recommendations:
        logger.info("No PO recommendations to write")
        return

    # Flatten recommendations to a table
    rows = []
    for rec in result.recommendations:
        for line in rec.lines:
            rows.append({
                "po_id": rec.po_id,
                "vendor_id": rec.vendor_id,
                "vendor_name": rec.vendor_name,
                "vendor_tier": rec.vendor_tier,
                "order_date": rec.order_date,
                "expected_delivery_date": rec.expected_delivery_date,
                "lead_time_days": rec.lead_time_days,
                "sku_id": line["sku_id"],
                "qty_ordered": line["qty_ordered"],
                "unit_cost": line["unit_cost"],
                "line_value": line["line_value"],
                "destination_store": line.get("destination_store", ""),
                "urgency": line.get("urgency", rec.urgency),
                "is_new_sku": line.get("is_new_sku", False),
                "lifecycle_stage": line.get("lifecycle_stage", ""),
                "po_total_qty": rec.total_qty,
                "po_total_value": rec.total_value,
                "moq_met": rec.moq_met,
                "mov_met": rec.mov_met,
                "status": rec.status,
            })

    df = pd.DataFrame(rows)

    con = duckdb.connect(config.db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS main_ml")
    con.execute(f"DROP TABLE IF EXISTS {config.output_table}")  # noqa: S608
    con.execute(f"""
        CREATE TABLE {config.output_table} AS
        SELECT * FROM df
    """)  # noqa: S608
    count = con.execute(f"SELECT count(*) FROM {config.output_table}").fetchone()[0]  # noqa: S608
    con.close()
    logger.info(f"Written {count} PO recommendation lines to {config.output_table}")


def run_po_pipeline(
    config: PurchaseOrderConfig,
    output_path: str | None = None,
    write_to_db: bool = True,
    order_date: date | None = None,
) -> PORecommendationResult:
    """Run the full PO recommendation pipeline.

    1. Load replenishment needs
    2. Load vendor performance data
    3. Generate PO recommendations
    4. Write to DB / CSV
    """
    logger.info("=" * 60)
    logger.info("PO Recommendation Engine v1")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Step 1: Load replenishment needs
    logger.info("Step 1: Loading replenishment needs")
    needs = load_replenishment_needs(config)
    if needs.empty:
        logger.warning("No replenishment needs found — run replenishment pipeline first")
        return PORecommendationResult()

    # Step 2: Load vendor data
    logger.info("Step 2: Loading vendor performance data")
    vendors = load_vendor_performance(config)
    if vendors.empty:
        logger.warning("No vendor data available")
        return PORecommendationResult()

    # Step 3: Generate recommendations
    logger.info("Step 3: Generating PO recommendations")
    result = generate_po_recommendations(needs, vendors, config, order_date)

    # Step 4: Write outputs
    if result.recommendations:
        if write_to_db:
            logger.info("Step 4: Writing to database")
            write_po_recommendations(result, config)

        if output_path:
            rows = []
            for rec in result.recommendations:
                for line in rec.lines:
                    rows.append({
                        "po_id": rec.po_id, "vendor_id": rec.vendor_id,
                        "sku_id": line["sku_id"], "qty": line["qty_ordered"],
                        "urgency": rec.urgency, "delivery_date": rec.expected_delivery_date,
                    })
            pd.DataFrame(rows).to_csv(output_path, index=False)
            logger.info(f"Written to {output_path}")

    _log_summary(result)
    return result


def _log_summary(result: PORecommendationResult):
    """Log PO recommendation summary."""
    logger.info("=" * 60)
    logger.info("PO Recommendation Summary")
    logger.info(f"  Total POs: {result.total_pos}")
    logger.info(f"  Total units: {result.total_units}")
    logger.info(f"  Total value: ₹{result.total_value:,.0f}")
    logger.info(f"  Vendors used: {result.vendors_used}")
    logger.info(f"  SKUs covered: {result.skus_covered}")
    if result.diagnostics:
        if result.diagnostics.get("moq_issues"):
            logger.warning(f"  MOQ issues: {result.diagnostics['moq_issues']} POs")
        if result.diagnostics.get("mov_issues"):
            logger.warning(f"  MOV issues: {result.diagnostics['mov_issues']} POs")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run PO recommendation pipeline")
    parser.add_argument("--db-path", default="data/dev.duckdb")
    parser.add_argument("--output", type=str, default=None, help="CSV output path")
    parser.add_argument("--no-db-write", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = PurchaseOrderConfig(db_path=args.db_path)
    result = run_po_pipeline(config, output_path=args.output, write_to_db=not args.no_db_write)

    if not result.recommendations:
        logger.info("No PO recommendations generated")
        sys.exit(0)

    logger.info(f"Pipeline complete: {result.total_pos} POs recommended")
    sys.exit(0)


if __name__ == "__main__":
    main()
