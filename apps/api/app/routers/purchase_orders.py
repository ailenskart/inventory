"""Purchase order API endpoints.

POST /purchase-orders/generate     — generate PO recommendations from replenishment needs
GET  /purchase-orders/recommended  — list recommended POs
GET  /purchase-orders/             — list all POs (from seed data)
POST /purchase-orders/create       — create a manual PO
GET  /purchase-orders/suggestions  — legacy alias for /recommended
"""

import logging
import os
from datetime import date

import duckdb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("LENSKART_DB_PATH", "data/dev.duckdb")


# ─── Request / Response models ────────────────────────────────────────────────


class POLineItem(BaseModel):
    sku_id: str
    qty: int
    unit_cost: float
    destination: str = "warehouse"


class POCreateRequest(BaseModel):
    vendor_id: str
    lines: list[POLineItem]
    requested_delivery_date: date | None = None


class POGenerateRequest(BaseModel):
    forecast_horizon_weeks: int = Field(12, ge=4, le=24)
    pad_to_moq: bool = True


class POGenerateResponse(BaseModel):
    status: str
    total_pos: int
    total_units: int
    total_value: float
    vendors_used: int
    skus_covered: int
    diagnostics: dict


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/generate", response_model=POGenerateResponse)
def generate_po_recommendations(request: POGenerateRequest):
    """Generate PO recommendations from replenishment pipeline output."""
    from services.purchase_orders.config import PurchaseOrderConfig
    from services.purchase_orders.pipeline import run_po_pipeline

    config = PurchaseOrderConfig(
        db_path=DB_PATH,
        forecast_horizon_weeks=request.forecast_horizon_weeks,
        pad_to_moq=request.pad_to_moq,
    )

    try:
        result = run_po_pipeline(config, write_to_db=True)
    except Exception as e:
        logger.exception("PO generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    return POGenerateResponse(
        status="success" if result.total_pos > 0 else "no_recommendations",
        total_pos=result.total_pos,
        total_units=result.total_units,
        total_value=result.total_value,
        vendors_used=result.vendors_used,
        skus_covered=result.skus_covered,
        diagnostics=result.diagnostics,
    )


@router.get("/recommended")
def get_recommended_pos(
    vendor_id: str | None = Query(None),
    urgency: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get current PO recommendations."""
    from services.purchase_orders.config import PurchaseOrderConfig

    config = PurchaseOrderConfig(db_path=DB_PATH)

    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        con.execute(f"SELECT 1 FROM {config.output_table} LIMIT 1")  # noqa: S608
    except Exception:
        try:
            con.close()
        except Exception:
            pass
        return {"recommendations": [], "count": 0, "total_value": 0.0}

    conditions = []
    params = []
    if vendor_id:
        conditions.append("vendor_id = ?")
        params.append(vendor_id)
    if urgency:
        conditions.append("urgency = ?")
        params.append(urgency)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT * FROM {config.output_table}
        {where}
        ORDER BY urgency, po_id
        LIMIT ?
    """  # noqa: S608

    df = con.execute(query, params + [limit]).fetchdf()
    con.close()

    records = df.to_dict(orient="records") if not df.empty else []
    total_value = float(df["line_value"].sum()) if not df.empty else 0.0

    return {
        "recommendations": records,
        "count": len(records),
        "total_value": round(total_value, 2),
    }


@router.get("/")
def list_purchase_orders(
    vendor_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=500),
):
    """List purchase orders from historical data."""
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        con.execute("SELECT 1 FROM main_staging.stg_purchase_orders LIMIT 1")
    except Exception:
        try:
            con.close()
        except Exception:
            pass
        return {"purchase_orders": [], "count": 0}

    conditions = []
    params = []
    if vendor_id:
        conditions.append("vendor_id = ?")
        params.append(vendor_id)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT po_id, vendor_id, status, order_date, expected_delivery_date,
               actual_delivery_date, total_qty, total_value, num_lines,
               delivery_delay_days
        FROM main_staging.stg_purchase_orders
        {where}
        ORDER BY order_date DESC
        LIMIT ?
    """  # noqa: S608

    df = con.execute(query, params + [limit]).fetchdf()
    con.close()

    return {
        "purchase_orders": df.to_dict(orient="records") if not df.empty else [],
        "count": len(df),
    }


@router.post("/create")
def create_purchase_order(request: POCreateRequest):
    """Create a new purchase order."""
    from services.purchase_orders.manager import PurchaseOrderManager

    manager = PurchaseOrderManager()
    lines = [
        {"sku_id": l.sku_id, "qty_ordered": l.qty, "unit_cost": l.unit_cost}
        for l in request.lines
    ]
    po = manager.create_draft(
        vendor_id=request.vendor_id,
        lines=lines,
        order_date=request.requested_delivery_date,
    )
    return po


@router.get("/suggestions")
def get_po_suggestions():
    """Get PO suggestions (alias for /recommended)."""
    return get_recommended_pos()
