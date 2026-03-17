"""Automated purchase order generation.

Groups replenishment recommendations by vendor, applies MOQ/MOV constraints,
and generates draft POs.
"""

from collections import defaultdict
from datetime import date, timedelta


def generate_purchase_orders(
    recommendations: list[dict],
    vendor_info: dict[str, dict],
    order_date: date | None = None,
) -> list[dict]:
    """Generate POs from replenishment recommendations.

    Args:
        recommendations: Output from replenishment optimizer
        vendor_info: {vendor_id: {moq, mov, avg_lead_time_days, unit_costs: {sku_id: cost}}}
        order_date: Date for the PO (defaults to today)

    Returns:
        List of draft PO dicts
    """
    if order_date is None:
        order_date = date.today()

    # Group by vendor
    vendor_groups: dict[str, list] = defaultdict(list)
    for rec in recommendations:
        vid = rec.get("vendor_id")
        if vid:
            vendor_groups[vid].append(rec)

    purchase_orders = []
    for vendor_id, items in vendor_groups.items():
        info = vendor_info.get(vendor_id, {})
        moq = info.get("moq", 0)
        mov = info.get("mov", 0.0)
        lead_time = info.get("avg_lead_time_days", 7)
        unit_costs = info.get("unit_costs", {})

        lines = []
        total_qty = 0
        total_value = 0.0

        for item in items:
            sku_id = item["sku_id"]
            qty = item["order_qty"]
            cost = unit_costs.get(sku_id, 0.0)
            lines.append({
                "sku_id": sku_id,
                "qty_ordered": qty,
                "unit_cost": cost,
                "destination_type": "store",
                "destination_id": item["store_id"],
            })
            total_qty += qty
            total_value += qty * cost

        # Check MOQ/MOV
        if total_qty < moq:
            # TODO: Decide whether to pad order or skip
            pass
        if total_value < mov:
            # TODO: Decide whether to add items or skip
            pass

        purchase_orders.append({
            "vendor_id": vendor_id,
            "order_date": order_date.isoformat(),
            "expected_delivery_date": (order_date + timedelta(days=lead_time)).isoformat(),
            "lines": lines,
            "total_qty": total_qty,
            "total_value": total_value,
            "status": "draft",
        })

    return purchase_orders
