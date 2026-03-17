"""Replenishment API endpoints."""

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class ReplenishmentPlan(BaseModel):
    store_id: str
    sku_id: str
    current_stock: int
    reorder_point: int
    recommended_qty: int
    source: str  # warehouse, vendor
    priority: str  # urgent, normal, low
    expected_delivery_date: date | None = None


@router.get("/plan")
def get_replenishment_plan(
    store_id: str | None = Query(None),
    region: str | None = Query(None),
    priority: str | None = Query(None),
):
    """Get replenishment recommendations."""
    # TODO: Wire to services/replenishment engine
    return {"plans": [], "total_skus": 0, "total_stores": 0}


@router.post("/execute")
def execute_replenishment(plan_ids: list[str]):
    """Approve and execute replenishment plans, generating POs or transfer orders."""
    # TODO: Create POs/transfers from approved plans
    return {"status": "accepted", "plans_executed": len(plan_ids)}
