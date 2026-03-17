"""Vendor intelligence API endpoints.

GET  /vendors/scorecard/{vendor_id} — individual vendor scorecard
GET  /vendors/scorecards             — all vendor scorecards ranked
GET  /vendors/portal/{vendor_id}     — vendor portal payload
"""

import logging
import os
from dataclasses import asdict

import duckdb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("LENSKART_DB_PATH", "data/dev.duckdb")


# ─── Response models ──────────────────────────────────────────────────────────


class VendorScorecardResponse(BaseModel):
    vendor_id: str
    vendor_name: str
    on_time_delivery_rate: float
    lead_time_adherence: float
    quality_pass_rate: float
    capacity_accuracy: float
    forecast_adherence: float
    composite_score: float
    tier: str
    total_pos: int
    received_pos: int
    total_units_ordered: int
    avg_delivery_delay_days: float
    total_skus: int
    active_skus: int
    is_active: bool


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _load_vendor_data() -> "pd.DataFrame":
    import pandas as pd

    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail="Database not available")

    con = duckdb.connect(DB_PATH, read_only=True)

    # Try performance mart first
    try:
        con.execute("SELECT 1 FROM main_marts.mart_vendor_performance LIMIT 1")
        df = con.execute("SELECT * FROM main_marts.mart_vendor_performance").fetchdf()
    except Exception:
        # Fall back to dim_vendor
        try:
            df = con.execute("""
                SELECT vendor_id, vendor_name, vendor_type,
                       avg_lead_time_days, min_order_value, min_order_qty,
                       reliability_score, is_active,
                       0 as total_pos, 0 as received_pos,
                       0 as total_units_ordered, 0 as total_po_value,
                       0.0 as avg_delivery_delay_days,
                       0 as late_deliveries, 0 as on_time_deliveries,
                       0 as total_skus, 0 as active_skus
                FROM main_dimensions.dim_vendor
            """).fetchdf()
        except Exception:
            con.close()
            raise HTTPException(status_code=503, detail="Vendor data not available")
    con.close()
    return df


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/scorecard/{vendor_id}", response_model=VendorScorecardResponse)
def get_vendor_scorecard(vendor_id: str):
    """Get performance scorecard for a specific vendor."""
    from ml.vendor.scorecard import build_vendor_scorecard

    df = _load_vendor_data()
    vendor_row = df[df["vendor_id"] == vendor_id]

    if vendor_row.empty:
        raise HTTPException(status_code=404, detail=f"Vendor {vendor_id} not found")

    sc = build_vendor_scorecard(vendor_row.iloc[0].to_dict())
    return VendorScorecardResponse(**asdict(sc))


@router.get("/scorecards")
def get_all_scorecards(
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    tier: str | None = Query(None),
    active_only: bool = Query(True),
):
    """Get scorecards for all vendors, ranked by composite score."""
    from ml.vendor.scorecard import build_all_scorecards

    df = _load_vendor_data()
    scorecards = build_all_scorecards(df)

    results = []
    for sc in sorted(scorecards, key=lambda s: s.composite_score, reverse=True):
        if sc.composite_score < min_score:
            continue
        if active_only and not sc.is_active:
            continue
        if tier and sc.tier != tier:
            continue
        results.append(asdict(sc))

    return {"scorecards": results, "count": len(results)}


@router.get("/portal/{vendor_id}")
def get_vendor_portal(vendor_id: str):
    """Get vendor portal payload with forecast visibility, open POs, and capacity."""
    from dataclasses import asdict

    from ml.vendor.portal import build_vendor_portal_payload
    from ml.vendor.scorecard import build_vendor_scorecard

    df = _load_vendor_data()
    vendor_row = df[df["vendor_id"] == vendor_id]

    if vendor_row.empty:
        raise HTTPException(status_code=404, detail=f"Vendor {vendor_id} not found")

    vendor_name = str(vendor_row.iloc[0].get("vendor_name", vendor_id))

    # Load open POs for this vendor
    open_po_data = []
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        pos = con.execute("""
            SELECT po_id, status, order_date, expected_delivery_date,
                   actual_delivery_date, total_qty, total_value
            FROM main_staging.stg_purchase_orders
            WHERE vendor_id = ? AND status NOT IN ('received', 'cancelled')
        """, [vendor_id]).fetchdf()
        con.close()
        if not pos.empty:
            open_po_data = pos.to_dict(orient="records")
    except Exception:
        pass

    # Build portal payload
    payload = build_vendor_portal_payload(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        open_po_data=open_po_data,
    )

    return asdict(payload)
