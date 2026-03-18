"""Replenishment API endpoints.

Provides:
- POST /replenishment/run: Trigger daily replenishment pipeline
- GET /replenishment/store/{store_id}: Recommendations for a specific store
- GET /replenishment/plan: All current recommendations with filtering
- POST /replenishment/execute: Approve and execute plans
"""

import logging
import os

import duckdb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("LENSKART_DB_PATH", "data/dev.duckdb")
RECO_TABLE = "main_ml.replenishment_recommendations"


class ReplenishmentRunRequest(BaseModel):
    target_days_of_cover: int = 28
    emergency_only: bool = False


class ReplenishmentRecord(BaseModel):
    sku_id: str
    destination_store: str
    source_location: str
    recommended_qty: int
    urgency: str
    reason_code: str
    reason_description: str
    on_hand_qty: int
    in_transit_qty: int
    reorder_point: float
    safety_stock: float
    current_days_of_cover: float
    expected_days_of_cover_after: float
    stockout_risk: float
    lost_sales_estimate: float
    category: str | None = None
    sku_type: str | None = None
    vendor_id: str | None = None


class ReplenishmentSummary(BaseModel):
    total_recommendations: int
    stores_affected: int
    skus_to_replenish: int
    total_units: int
    emergency_count: int
    urgent_count: int
    normal_count: int


class RunResponse(BaseModel):
    status: str
    message: str
    summary: ReplenishmentSummary | None = None


def _get_connection(read_only: bool = True):
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail="Database not available")
    return duckdb.connect(DB_PATH, read_only=read_only)


def _has_recommendations() -> bool:
    try:
        con = _get_connection()
        con.execute(f"SELECT 1 FROM {RECO_TABLE} LIMIT 1")  # noqa: S608
        con.close()
        return True
    except Exception:
        return False


@router.get("/store/{store_id}", response_model=list[ReplenishmentRecord])
def get_store_replenishment(
    store_id: str,
    urgency: str | None = Query(None),
    limit: int = Query(100, le=1000),
):
    """Get replenishment recommendations for a specific store."""
    if not _has_recommendations():
        raise HTTPException(status_code=404, detail="No recommendations available. Run POST /replenishment/run first.")

    con = _get_connection()
    conditions = ["destination_store = $1"]
    params = [store_id]
    idx = 2

    if urgency:
        conditions.append(f"urgency = ${idx}")
        params.append(urgency)
        idx += 1

    where = " AND ".join(conditions)
    results = con.execute(f"""
        SELECT sku_id, destination_store, source_location, recommended_qty,
               urgency, reason_code, reason_description,
               on_hand_qty, in_transit_qty, reorder_point, safety_stock,
               current_days_of_cover, expected_days_of_cover_after,
               stockout_risk, lost_sales_estimate,
               category, sku_type, vendor_id
        FROM {RECO_TABLE}
        WHERE {where}
        ORDER BY urgency_rank, lost_sales_estimate DESC
        LIMIT ${idx}
    """, params + [limit]).fetchdf()  # noqa: S608
    con.close()

    if results.empty:
        raise HTTPException(status_code=404, detail=f"No recommendations for store {store_id}")

    return results.to_dict(orient="records")


@router.get("/plan", response_model=dict)
def get_replenishment_plan(
    store_id: str | None = Query(None),
    region: str | None = Query(None),
    urgency: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(200, le=2000),
):
    """Get replenishment recommendations with optional filters."""
    if not _has_recommendations():
        return {"plans": [], "total_skus": 0, "total_stores": 0}

    con = _get_connection()
    conditions = []
    params = []
    idx = 1

    if store_id:
        conditions.append(f"destination_store = ${idx}")
        params.append(store_id)
        idx += 1
    if region:
        conditions.append(f"store_cluster LIKE ${idx}")
        params.append(f"%{region}%")
        idx += 1
    if urgency:
        conditions.append(f"urgency = ${idx}")
        params.append(urgency)
        idx += 1
    if category:
        conditions.append(f"category = ${idx}")
        params.append(category)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    results = con.execute(f"""
        SELECT sku_id, destination_store, source_location, recommended_qty,
               urgency, reason_code, reason_description,
               on_hand_qty, in_transit_qty, reorder_point, safety_stock,
               current_days_of_cover, expected_days_of_cover_after,
               stockout_risk, lost_sales_estimate,
               category, sku_type, vendor_id
        FROM {RECO_TABLE}
        {where}
        ORDER BY urgency_rank, lost_sales_estimate DESC
        LIMIT ${idx}
    """, params + [limit]).fetchdf()  # noqa: S608
    con.close()

    return {
        "plans": results.to_dict(orient="records"),
        "total_skus": int(results["sku_id"].nunique()) if not results.empty else 0,
        "total_stores": int(results["destination_store"].nunique()) if not results.empty else 0,
    }


@router.post("/run", response_model=RunResponse)
def trigger_replenishment_run(request: ReplenishmentRunRequest):
    """Trigger daily replenishment pipeline."""
    try:
        from services.replenishment.config import ReplenishmentConfig
        from services.replenishment.pipeline import run_replenishment_pipeline

        config = ReplenishmentConfig(
            db_path=DB_PATH,
            target_days_of_cover=request.target_days_of_cover,
        )

        recommendations = run_replenishment_pipeline(config, write_to_db=True)

        if recommendations.empty:
            return RunResponse(status="success", message="No replenishment needed — all stock levels healthy")

        if request.emergency_only:
            recommendations = recommendations[recommendations["urgency"] == "emergency"]

        return RunResponse(
            status="success",
            message=f"Generated {len(recommendations)} recommendations",
            summary=ReplenishmentSummary(
                total_recommendations=len(recommendations),
                stores_affected=int(recommendations["destination_store"].nunique()),
                skus_to_replenish=int(recommendations["sku_id"].nunique()),
                total_units=int(recommendations["recommended_qty"].sum()),
                emergency_count=int((recommendations["urgency"] == "emergency").sum()),
                urgent_count=int((recommendations["urgency"] == "urgent").sum()),
                normal_count=int((recommendations["urgency"] == "normal").sum()),
            ),
        )
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Dependencies not available: {e}")
    except Exception as e:
        logger.exception("Replenishment run failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
def execute_replenishment(plan_ids: list[str]):
    """Approve and execute replenishment plans, generating POs or transfer orders."""
    # TODO: Create POs/transfers from approved plans
    return {"status": "accepted", "plans_executed": len(plan_ids)}
