"""Automated purchase order generation.

Groups replenishment recommendations by vendor, applies MOQ/MOV constraints,
handles repeat-SKU vs new-SKU logic, and generates draft POs.

Open PO support: can generate capacity-reservation POs over a rolling horizon
where actual release quantities are confirmed closer to need date.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def generate_purchase_orders(
    recommendations: list[dict],
    vendor_info: dict[str, dict],
    order_date: date | None = None,
    pad_to_moq: bool = True,
    default_unit_cost: float = 500.0,
) -> list[dict]:
    """Generate POs from replenishment recommendations.

    Args:
        recommendations: Output from replenishment engine. Each dict needs:
            vendor_id, sku_id, recommended_qty (or order_qty),
            destination_store (or store_id), urgency, lifecycle_stage.
        vendor_info: {vendor_id: {moq, mov, avg_lead_time_days, unit_costs: {sku_id: cost}}}
        order_date: Date for the PO (defaults to today).
        pad_to_moq: If True, pad PO quantity to meet vendor MOQ.
        default_unit_cost: Fallback unit cost when vendor costs unavailable.

    Returns:
        List of draft PO dicts.
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
            sku_id = item.get("sku_id", "")
            qty = item.get("recommended_qty", item.get("order_qty", 0))
            cost = unit_costs.get(sku_id, default_unit_cost)
            lifecycle = item.get("lifecycle_stage", "active")
            is_new = lifecycle in ("new", "launch")

            destination = item.get("destination_store", item.get("store_id", "warehouse"))

            lines.append({
                "sku_id": sku_id,
                "qty_ordered": qty,
                "unit_cost": cost,
                "line_value": round(qty * cost, 2),
                "destination_type": "store" if destination != "warehouse" else "warehouse",
                "destination_id": destination,
                "is_new_sku": is_new,
                "urgency": item.get("urgency", "normal"),
            })
            total_qty += qty
            total_value += qty * cost

        # Apply MOQ — pad the largest line to meet minimum
        if pad_to_moq and moq > 0 and total_qty < moq:
            deficit = moq - total_qty
            if lines:
                # Pad the highest-urgency line
                lines.sort(key=lambda l: {"emergency": 0, "urgent": 1, "normal": 2, "low": 3}.get(l["urgency"], 3))
                lines[0]["qty_ordered"] += deficit
                lines[0]["line_value"] = round(lines[0]["qty_ordered"] * lines[0]["unit_cost"], 2)
                total_qty = moq
                total_value = sum(l["line_value"] for l in lines)
            logger.info(f"Padded PO for {vendor_id} by {deficit} units to meet MOQ={moq}")

        # Check MOV — flag but don't skip (let caller decide)
        below_mov = mov > 0 and total_value < mov

        po_id = f"PO-{vendor_id}-{order_date.isoformat()}"

        purchase_orders.append({
            "po_id": po_id,
            "vendor_id": vendor_id,
            "order_date": order_date.isoformat(),
            "expected_delivery_date": (order_date + timedelta(days=lead_time)).isoformat(),
            "lead_time_days": lead_time,
            "lines": lines,
            "total_qty": total_qty,
            "total_value": round(total_value, 2),
            "num_lines": len(lines),
            "status": "draft",
            "moq_met": total_qty >= moq if moq > 0 else True,
            "mov_met": not below_mov,
            "has_new_skus": any(l["is_new_sku"] for l in lines),
        })

    logger.info(
        f"Generated {len(purchase_orders)} draft POs from "
        f"{len(recommendations)} recommendations"
    )
    return purchase_orders


def generate_open_po_plan(
    vendor_id: str,
    sku_forecasts: list[dict],
    horizon_weeks: int = 12,
    release_cadence_weeks: int = 2,
    start_date: date | None = None,
) -> dict:
    """Generate an open PO plan with capacity reservation over a rolling horizon.

    Open POs reserve capacity at the vendor level. Actual release quantities
    are confirmed every `release_cadence_weeks`.

    Args:
        vendor_id: Target vendor.
        sku_forecasts: List of {sku_id, weekly_forecast, unit_cost}.
        horizon_weeks: Total horizon for capacity reservation (8–12).
        release_cadence_weeks: How often to confirm/release quantities.
        start_date: Plan start date.

    Returns:
        Open PO plan dict with period-by-period releases.
    """
    if start_date is None:
        start_date = date.today()

    periods = []
    total_committed = 0
    total_value = 0.0

    for offset in range(0, horizon_weeks, release_cadence_weeks):
        period_start = start_date + timedelta(weeks=offset)
        period_end = period_start + timedelta(weeks=release_cadence_weeks)
        # First period is "confirmed", rest are "forecast"
        status = "confirmed" if offset == 0 else "forecast"

        period_lines = []
        period_qty = 0
        period_value = 0.0

        for sf in sku_forecasts:
            qty = int(sf.get("weekly_forecast", 0) * release_cadence_weeks)
            cost = float(sf.get("unit_cost", 500.0))
            period_lines.append({
                "sku_id": sf["sku_id"],
                "qty": qty,
                "unit_cost": cost,
                "line_value": round(qty * cost, 2),
            })
            period_qty += qty
            period_value += qty * cost

        periods.append({
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "status": status,
            "lines": period_lines,
            "total_qty": period_qty,
            "total_value": round(period_value, 2),
        })
        total_committed += period_qty
        total_value += period_value

    return {
        "vendor_id": vendor_id,
        "plan_type": "open_po",
        "horizon_weeks": horizon_weeks,
        "release_cadence_weeks": release_cadence_weeks,
        "start_date": start_date.isoformat(),
        "end_date": (start_date + timedelta(weeks=horizon_weeks)).isoformat(),
        "periods": periods,
        "total_committed_qty": total_committed,
        "total_committed_value": round(total_value, 2),
        "num_periods": len(periods),
    }
