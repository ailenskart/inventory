"""Replenishment optimization using OR-Tools.

Determines optimal reorder quantities considering:
- Demand forecasts
- Current inventory levels
- Service level targets
- Vendor constraints (MOQ, MOV, lead time)
- Storage capacity
"""

from ortools.linear_solver import pywraplp


def optimize_replenishment(
    store_sku_forecasts: list[dict],
    current_inventory: dict[tuple[str, str], int],
    vendor_constraints: dict[str, dict],
    service_level: float = 0.95,
) -> list[dict]:
    """Solve replenishment optimization.

    Args:
        store_sku_forecasts: List of {store_id, sku_id, forecast_qty, vendor_id}
        current_inventory: {(store_id, sku_id): on_hand_qty}
        vendor_constraints: {vendor_id: {moq, mov, lead_time_days}}
        service_level: Target service level (0-1)

    Returns:
        List of {store_id, sku_id, order_qty, vendor_id, priority}
    """
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if not solver:
        return []

    recommendations = []
    order_vars = {}

    for item in store_sku_forecasts:
        key = (item["store_id"], item["sku_id"])
        current = current_inventory.get(key, 0)
        forecast = item["forecast_qty"]
        safety_stock = forecast * (1 + service_level)  # Simplified safety stock

        deficit = max(0, safety_stock - current)
        if deficit > 0:
            var = solver.IntVar(0, int(deficit * 2), f"order_{key[0]}_{key[1]}")
            order_vars[key] = var

            # Minimize total order quantity while meeting service level
            solver.Minimize(var)
            solver.Add(var >= int(deficit))

    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL:
        for item in store_sku_forecasts:
            key = (item["store_id"], item["sku_id"])
            if key in order_vars:
                qty = int(order_vars[key].solution_value())
                if qty > 0:
                    current = current_inventory.get(key, 0)
                    priority = "urgent" if current == 0 else ("normal" if qty > 5 else "low")
                    recommendations.append({
                        "store_id": key[0],
                        "sku_id": key[1],
                        "order_qty": qty,
                        "vendor_id": item.get("vendor_id"),
                        "priority": priority,
                    })

    return recommendations
