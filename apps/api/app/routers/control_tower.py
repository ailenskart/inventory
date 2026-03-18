"""Control Tower summary endpoint.

Provides a single unified view of the entire retail intelligence platform:
- Forecast accuracy snapshot
- Stockout risk summary
- Top replenishment actions
- Top transfer actions
- Vendor capacity alerts
- PO recommendations summary
- Lifecycle stage distribution
"""

import logging
import os

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("LENSKART_DB_PATH", "data/dev.duckdb")


class ForecastSnapshot(BaseModel):
    total_forecasts: int = 0
    stores_covered: int = 0
    skus_covered: int = 0
    avg_point_forecast: float = 0.0
    model_used: str = "N/A"


class StockoutRiskSummary(BaseModel):
    total_positions: int = 0
    stockout_count: int = 0
    critical_count: int = 0
    low_count: int = 0
    healthy_count: int = 0
    excess_count: int = 0
    stockout_rate: float = 0.0


class ReplenishmentSnapshot(BaseModel):
    total_recommendations: int = 0
    stores_affected: int = 0
    emergency_count: int = 0
    urgent_count: int = 0
    total_units: int = 0
    top_actions: list[dict] = []


class TransferSnapshot(BaseModel):
    total_transfers: int = 0
    total_units: int = 0
    net_value: float = 0.0
    top_actions: list[dict] = []


class VendorAlerts(BaseModel):
    total_vendors: int = 0
    low_score_vendors: list[dict] = []
    avg_composite_score: float = 0.0


class POSnapshot(BaseModel):
    total_pos: int = 0
    total_units: int = 0
    total_value: float = 0.0
    vendors_used: int = 0


class LifecycleSnapshot(BaseModel):
    total_classified: int = 0
    stage_distribution: dict[str, int] = {}
    action_distribution: dict[str, int] = {}
    avg_confidence: float = 0.0


class ControlTowerResponse(BaseModel):
    status: str = "ok"
    forecast: ForecastSnapshot = ForecastSnapshot()
    stockout_risk: StockoutRiskSummary = StockoutRiskSummary()
    replenishment: ReplenishmentSnapshot = ReplenishmentSnapshot()
    transfers: TransferSnapshot = TransferSnapshot()
    vendor_alerts: VendorAlerts = VendorAlerts()
    purchase_orders: POSnapshot = POSnapshot()
    lifecycle: LifecycleSnapshot = LifecycleSnapshot()


@router.get("/summary", response_model=ControlTowerResponse)
def get_control_tower_summary(
    db_path: str = Query(DB_PATH, include_in_schema=False),
) -> ControlTowerResponse:
    """Get a unified control tower summary across all platform modules.

    Returns a single snapshot of the entire retail intelligence platform state.
    """
    import duckdb

    response = ControlTowerResponse()

    try:
        con = duckdb.connect(db_path, read_only=True)
    except Exception:
        response.status = "database_unavailable"
        return response

    # ── Forecast snapshot ────────────────────────────────────────────────
    try:
        row = con.execute("""
            SELECT count(*) as cnt,
                   count(DISTINCT store_id) as stores,
                   count(DISTINCT sku_id) as skus,
                   avg(point_forecast) as avg_pf,
                   mode(model_used) as model
            FROM main_ml.demand_forecasts
        """).fetchone()
        if row and row[0] > 0:
            response.forecast = ForecastSnapshot(
                total_forecasts=int(row[0]),
                stores_covered=int(row[1]),
                skus_covered=int(row[2]),
                avg_point_forecast=round(float(row[3]), 2),
                model_used=str(row[4]) if row[4] else "N/A",
            )
    except Exception:
        pass

    # ── Stockout risk ────────────────────────────────────────────────────
    try:
        rows = con.execute("""
            SELECT inventory_status, count(*) as cnt
            FROM main_marts.mart_inventory_position
            GROUP BY inventory_status
        """).fetchall()
        if rows:
            status_counts = {r[0]: int(r[1]) for r in rows}
            total = sum(status_counts.values())
            stockout = status_counts.get("stockout", 0) + status_counts.get("stockout_pending_receipt", 0)
            response.stockout_risk = StockoutRiskSummary(
                total_positions=total,
                stockout_count=stockout,
                critical_count=status_counts.get("critical", 0),
                low_count=status_counts.get("low", 0),
                healthy_count=status_counts.get("healthy", 0),
                excess_count=status_counts.get("excess", 0) + status_counts.get("dead_stock", 0),
                stockout_rate=round(stockout / max(total, 1), 4),
            )
    except Exception:
        pass

    # ── Replenishment snapshot ───────────────────────────────────────────
    try:
        row = con.execute("""
            SELECT count(*) as cnt,
                   count(DISTINCT destination_store) as stores,
                   sum(CASE WHEN urgency = 'emergency' THEN 1 ELSE 0 END) as emergency,
                   sum(CASE WHEN urgency = 'urgent' THEN 1 ELSE 0 END) as urgent,
                   sum(recommended_qty) as total_units
            FROM main_ml.replenishment_recommendations
        """).fetchone()
        if row and row[0] > 0:
            top = con.execute("""
                SELECT sku_id, destination_store, recommended_qty, urgency, reason_code
                FROM main_ml.replenishment_recommendations
                ORDER BY urgency_rank, lost_sales_estimate DESC
                LIMIT 5
            """).fetchdf().to_dict(orient="records")
            response.replenishment = ReplenishmentSnapshot(
                total_recommendations=int(row[0]),
                stores_affected=int(row[1]),
                emergency_count=int(row[2]),
                urgent_count=int(row[3]),
                total_units=int(row[4]),
                top_actions=top,
            )
    except Exception:
        pass

    # ── Transfer snapshot ────────────────────────────────────────────────
    try:
        row = con.execute("""
            SELECT count(*) as cnt,
                   sum(qty) as total_units,
                   sum(net_value) as net_val
            FROM main_ml.transfer_recommendations
        """).fetchone()
        if row and row[0] > 0:
            top = con.execute("""
                SELECT from_store_id, to_store_id, sku_id, qty, reason, net_value
                FROM main_ml.transfer_recommendations
                ORDER BY net_value DESC
                LIMIT 5
            """).fetchdf().to_dict(orient="records")
            response.transfers = TransferSnapshot(
                total_transfers=int(row[0]),
                total_units=int(row[1]),
                net_value=round(float(row[2]), 2),
                top_actions=top,
            )
    except Exception:
        pass

    # ── Vendor alerts ────────────────────────────────────────────────────
    try:
        rows = con.execute("""
            SELECT vendor_id, vendor_name, reliability_score
            FROM main_marts.mart_vendor_performance
            ORDER BY reliability_score
        """).fetchdf()
        if not rows.empty:
            avg_score = float(rows["reliability_score"].mean())
            low_vendors = rows[rows["reliability_score"] < 0.7]
            response.vendor_alerts = VendorAlerts(
                total_vendors=len(rows),
                low_score_vendors=low_vendors.to_dict(orient="records") if not low_vendors.empty else [],
                avg_composite_score=round(avg_score, 3),
            )
    except Exception:
        pass

    # ── PO snapshot ──────────────────────────────────────────────────────
    try:
        row = con.execute("""
            SELECT count(DISTINCT po_id) as pos,
                   sum(qty_ordered) as units,
                   sum(line_value) as value,
                   count(DISTINCT vendor_id) as vendors
            FROM main_ml.po_recommendations
        """).fetchone()
        if row and row[0] > 0:
            response.purchase_orders = POSnapshot(
                total_pos=int(row[0]),
                total_units=int(row[1]),
                total_value=round(float(row[2]), 2),
                vendors_used=int(row[3]),
            )
    except Exception:
        pass

    # ── Lifecycle snapshot ───────────────────────────────────────────────
    try:
        rows = con.execute("""
            SELECT lifecycle_stage, count(*) as cnt
            FROM main_ml.lifecycle_classifications
            GROUP BY lifecycle_stage
        """).fetchall()
        if rows:
            stage_dist = {r[0]: int(r[1]) for r in rows}
            avg_conf = con.execute(
                "SELECT avg(confidence) FROM main_ml.lifecycle_classifications"
            ).fetchone()[0]

            action_rows = con.execute("""
                SELECT recommended_action, count(*) as cnt
                FROM main_ml.lifecycle_classifications
                GROUP BY recommended_action
            """).fetchall()
            action_dist = {r[0]: int(r[1]) for r in action_rows}

            response.lifecycle = LifecycleSnapshot(
                total_classified=sum(stage_dist.values()),
                stage_distribution=stage_dist,
                action_distribution=action_dist,
                avg_confidence=round(float(avg_conf), 3) if avg_conf else 0.0,
            )
    except Exception:
        pass

    con.close()
    return response
