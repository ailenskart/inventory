"""Purchase order lifecycle management.

Handles PO creation, approval workflow, and receipt tracking.
"""

from datetime import date
from typing import Any


class PurchaseOrderManager:
    """Manages PO lifecycle from draft to received."""

    def __init__(self):
        # TODO: Wire to database
        self._orders: dict[str, dict] = {}

    def create_draft(self, vendor_id: str, lines: list[dict], order_date: date | None = None) -> dict:
        """Create a draft PO."""
        po_id = f"PO-{vendor_id}-{(order_date or date.today()).isoformat()}"
        po = {
            "po_id": po_id,
            "vendor_id": vendor_id,
            "status": "draft",
            "order_date": (order_date or date.today()).isoformat(),
            "lines": lines,
            "total_qty": sum(l.get("qty_ordered", 0) for l in lines),
            "total_value": sum(l.get("qty_ordered", 0) * l.get("unit_cost", 0) for l in lines),
        }
        self._orders[po_id] = po
        return po

    def submit(self, po_id: str) -> dict:
        """Submit a draft PO for approval."""
        po = self._orders.get(po_id)
        if not po:
            raise ValueError(f"PO {po_id} not found")
        if po["status"] != "draft":
            raise ValueError(f"PO {po_id} is not in draft status")
        po["status"] = "submitted"
        return po

    def approve(self, po_id: str) -> dict:
        """Approve a submitted PO."""
        po = self._orders.get(po_id)
        if not po:
            raise ValueError(f"PO {po_id} not found")
        if po["status"] != "submitted":
            raise ValueError(f"PO {po_id} is not in submitted status")
        po["status"] = "approved"
        return po

    def record_receipt(self, po_id: str, received_lines: list[dict]) -> dict:
        """Record goods receipt against a PO."""
        po = self._orders.get(po_id)
        if not po:
            raise ValueError(f"PO {po_id} not found")
        po["received_lines"] = received_lines
        po["total_received"] = sum(l.get("qty_received", 0) for l in received_lines)
        if po["total_received"] >= po["total_qty"]:
            po["status"] = "received"
        return po
