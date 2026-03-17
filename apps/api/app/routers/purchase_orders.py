"""Purchase order API endpoints."""

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class POLineItem(BaseModel):
    sku_id: str
    qty: int
    unit_cost: float
    destination: str  # warehouse or store_id


class POCreateRequest(BaseModel):
    vendor_id: str
    lines: list[POLineItem]
    requested_delivery_date: date | None = None


@router.post("/create")
def create_purchase_order(request: POCreateRequest):
    """Create a new purchase order."""
    # TODO: Validate vendor, check MOQ/MOV, persist PO
    return {"po_id": "PO_PLACEHOLDER", "status": "draft", "total_qty": sum(l.qty for l in request.lines)}


@router.get("/")
def list_purchase_orders(
    vendor_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=500),
):
    """List purchase orders."""
    # TODO: Query PO table
    return {"purchase_orders": [], "count": 0}


@router.get("/suggestions")
def get_po_suggestions():
    """Get automated PO suggestions based on forecasts and current inventory."""
    # TODO: Wire to ml/vendor + services/purchase_orders
    return {"suggestions": []}
