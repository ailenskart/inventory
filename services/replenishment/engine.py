"""Core replenishment engine.

Computes reorder points, safety stock, order-up-to levels, and generates
replenishment recommendations per SKU × Store.

Differentiates between:
1. Display dummy inventory — maintain display wall, fixed replenishment
2. Direct sell-through inventory — forecast-driven, service-level-aware
3. Prescription fulfillment — order-capture pipeline, lighter stocking

Pull-based, forecast-driven replenishment:
  Order-Up-To Level = (Daily Demand × Review Period) + Safety Stock + Pipeline Stock
  Reorder Point = (Daily Demand × Lead Time) + Safety Stock
  Safety Stock = z(SL) × σ_demand × √(Lead Time)
  Recommended Qty = max(0, Order-Up-To - On-Hand - In-Transit)
  Final Qty = round_up_to_case_pack(max(Recommended Qty, MOQ))
"""

import logging
import math

import numpy as np
import pandas as pd

from services.replenishment.config import (
    REASON_CODES,
    URGENCY_EMERGENCY,
    URGENCY_LOW,
    URGENCY_NORMAL,
    URGENCY_URGENT,
    ReplenishmentConfig,
)

logger = logging.getLogger(__name__)


def get_z_score(service_level: float, config: ReplenishmentConfig) -> float:
    """Look up z-score for a given service level."""
    if service_level in config.z_scores:
        return config.z_scores[service_level]
    # Linear interpolation between nearest known values
    levels = sorted(config.z_scores.keys())
    for i in range(len(levels) - 1):
        if levels[i] <= service_level <= levels[i + 1]:
            frac = (service_level - levels[i]) / (levels[i + 1] - levels[i])
            return config.z_scores[levels[i]] + frac * (
                config.z_scores[levels[i + 1]] - config.z_scores[levels[i]]
            )
    return 1.645  # Default to 95%


def compute_safety_stock(
    demand_std_daily: float,
    lead_time_days: float,
    z_score: float,
) -> float:
    """Compute safety stock.

    Safety Stock = z × σ_demand × √(lead_time)
    """
    if demand_std_daily <= 0 or lead_time_days <= 0:
        return 0.0
    return z_score * demand_std_daily * math.sqrt(lead_time_days)


def compute_reorder_point(
    avg_daily_demand: float,
    lead_time_days: float,
    safety_stock: float,
) -> float:
    """Compute reorder point.

    ROP = (avg_daily_demand × lead_time) + safety_stock
    """
    return (avg_daily_demand * lead_time_days) + safety_stock


def compute_order_up_to_level(
    avg_daily_demand: float,
    target_days_of_cover: int,
    safety_stock: float,
) -> float:
    """Compute order-up-to level.

    OUT = (avg_daily_demand × target_days) + safety_stock
    """
    return (avg_daily_demand * target_days_of_cover) + safety_stock


def round_up_to_case_pack(qty: float, case_pack: int) -> int:
    """Round quantity up to nearest case pack multiple."""
    if case_pack <= 1:
        return max(0, math.ceil(qty))
    return max(0, math.ceil(qty / case_pack) * case_pack)


def apply_moq(qty: int, moq: int) -> int:
    """Apply minimum order quantity. If qty > 0 but < MOQ, bump to MOQ."""
    if qty <= 0:
        return 0
    return max(qty, moq)


def compute_stockout_risk(
    on_hand_qty: int,
    in_transit_qty: int,
    avg_daily_demand: float,
    demand_std_daily: float,
    lead_time_days: float,
) -> float:
    """Estimate probability of stockout before next replenishment arrives.

    Uses normal distribution approximation:
    P(stockout) = P(demand_during_LT > available_stock)
    """
    if avg_daily_demand <= 0:
        return 0.0

    available = on_hand_qty + in_transit_qty
    demand_during_lt = avg_daily_demand * lead_time_days
    std_during_lt = demand_std_daily * math.sqrt(lead_time_days) if demand_std_daily > 0 else 0.0

    if std_during_lt <= 0:
        return 0.0 if available >= demand_during_lt else 1.0

    # Z = (available - demand_during_lt) / std_during_lt
    z = (available - demand_during_lt) / std_during_lt
    # P(stockout) = P(Z < -z) = Phi(-z) ≈ using scipy-free approximation
    return _norm_cdf(-z)


def _norm_cdf(x: float) -> float:
    """Approximate standard normal CDF (Abramowitz & Stegun)."""
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def estimate_lost_sales(
    stockout_risk: float,
    avg_daily_demand: float,
    lead_time_days: float,
    unit_price: float,
) -> float:
    """Estimate expected lost sales value during lead time.

    E[lost_sales] = P(stockout) × avg_demand_during_LT × unit_price
    """
    if stockout_risk <= 0 or avg_daily_demand <= 0:
        return 0.0
    expected_demand_during_lt = avg_daily_demand * lead_time_days
    return stockout_risk * expected_demand_during_lt * unit_price


def compute_days_of_cover(
    on_hand_qty: int,
    in_transit_qty: int,
    avg_daily_demand: float,
) -> float:
    """Compute current days of cover (DOC)."""
    if avg_daily_demand <= 0:
        return float("inf") if (on_hand_qty + in_transit_qty) > 0 else 0.0
    return (on_hand_qty + in_transit_qty) / avg_daily_demand


def generate_recommendations(
    positions: pd.DataFrame,
    config: ReplenishmentConfig,
) -> pd.DataFrame:
    """Generate replenishment recommendations for all SKU × Store positions.

    Args:
        positions: DataFrame with columns:
            store_id, sku_id, on_hand_qty, in_transit_qty, available_qty,
            avg_weekly_demand, demand_std_weekly, lead_time_days, moq, case_pack,
            store_cluster, sku_type, fulfillment_type, is_display_only,
            category, vendor_id, mrp, store_capacity, current_store_units,
            point_forecast (weekly), upper_bound (weekly)
        config: Replenishment configuration

    Returns:
        DataFrame of recommendations with:
            sku_id, source_location, destination_store, recommended_qty,
            urgency, reason_code, expected_days_of_cover_after
    """
    if positions.empty:
        return _empty_recommendations()

    recs = []
    for _, row in positions.iterrows():
        rec = _compute_single_recommendation(row, config)
        if rec is not None:
            recs.append(rec)

    if not recs:
        return _empty_recommendations()

    result = pd.DataFrame(recs)
    result = result.sort_values(
        ["urgency_rank", "lost_sales_estimate"],
        ascending=[True, False],
    )

    logger.info(
        f"Generated {len(result)} replenishment recommendations: "
        f"{(result['urgency'] == URGENCY_EMERGENCY).sum()} emergency, "
        f"{(result['urgency'] == URGENCY_URGENT).sum()} urgent, "
        f"{(result['urgency'] == URGENCY_NORMAL).sum()} normal, "
        f"{(result['urgency'] == URGENCY_LOW).sum()} low"
    )

    return result


def _compute_single_recommendation(
    row: pd.Series,
    config: ReplenishmentConfig,
) -> dict | None:
    """Compute recommendation for a single SKU × Store."""
    store_id = row["store_id"]
    sku_id = row["sku_id"]
    is_display_only = bool(row.get("is_display_only", 0))
    fulfillment_type = row.get("fulfillment_type", "direct_sell")

    on_hand = int(row.get("on_hand_qty", 0))
    in_transit = int(row.get("in_transit_qty", 0))
    available = on_hand + in_transit

    # --- Display dummy path ---
    if is_display_only:
        return _compute_display_recommendation(row, config)

    # --- Sell-through / prescription path ---
    # Demand parameters (convert weekly to daily)
    avg_weekly = float(row.get("point_forecast", row.get("avg_weekly_demand", 0)))
    upper_weekly = float(row.get("upper_bound", avg_weekly * 1.3))
    demand_std_weekly = float(row.get("demand_std_weekly", (upper_weekly - avg_weekly) / 1.645))

    avg_daily = avg_weekly / 7.0
    demand_std_daily = demand_std_weekly / math.sqrt(7.0) if demand_std_weekly > 0 else 0.0

    # Lead time
    lead_time = float(row.get("lead_time_days", config.default_lead_time_days))

    # Service level based on store cluster
    store_cluster = row.get("store_cluster", "")
    service_level = config.service_levels.get(store_cluster, config.default_service_level)
    z = get_z_score(service_level, config)

    # Compute safety stock and reorder point
    safety_stock = compute_safety_stock(demand_std_daily, lead_time, z)
    rop = compute_reorder_point(avg_daily, lead_time, safety_stock)
    out_level = compute_order_up_to_level(avg_daily, config.target_days_of_cover, safety_stock)

    # No order needed if above reorder point
    if available > rop:
        return None

    # Recommended quantity
    raw_qty = out_level - available
    if raw_qty <= 0:
        return None

    # Apply MOQ and case pack
    moq = int(row.get("moq", config.default_moq))
    case_pack = int(row.get("case_pack", config.default_case_pack))
    qty = round_up_to_case_pack(raw_qty, case_pack)
    qty = apply_moq(qty, moq)

    # Apply store capacity constraint
    store_capacity = float(row.get("store_capacity", float("inf")))
    current_units = float(row.get("current_store_units", on_hand))
    max_capacity_units = max(0, store_capacity * config.max_capacity_utilization - current_units)
    if max_capacity_units < qty and max_capacity_units > 0:
        qty = round_up_to_case_pack(max_capacity_units, case_pack)
    elif max_capacity_units <= 0:
        return None  # Store at capacity

    # Stockout risk
    stockout_risk = compute_stockout_risk(
        on_hand, in_transit, avg_daily, demand_std_daily, lead_time
    )

    # Lost sales estimate
    mrp = float(row.get("mrp", 0))
    lost_sales = estimate_lost_sales(stockout_risk, avg_daily, lead_time, mrp)

    # Days of cover
    current_doc = compute_days_of_cover(on_hand, in_transit, avg_daily)
    after_doc = compute_days_of_cover(on_hand + qty, in_transit, avg_daily)

    # Urgency and reason
    urgency, reason = _determine_urgency_and_reason(
        on_hand, in_transit, current_doc, stockout_risk, config
    )

    urgency_rank = {
        URGENCY_EMERGENCY: 0, URGENCY_URGENT: 1,
        URGENCY_NORMAL: 2, URGENCY_LOW: 3,
    }.get(urgency, 3)

    return {
        "sku_id": sku_id,
        "destination_store": store_id,
        "source_location": config.default_source,
        "recommended_qty": qty,
        "urgency": urgency,
        "urgency_rank": urgency_rank,
        "reason_code": reason,
        "reason_description": REASON_CODES.get(reason, reason),
        "on_hand_qty": on_hand,
        "in_transit_qty": in_transit,
        "reorder_point": round(rop, 1),
        "safety_stock": round(safety_stock, 1),
        "order_up_to_level": round(out_level, 1),
        "avg_daily_demand": round(avg_daily, 2),
        "current_days_of_cover": round(current_doc, 1),
        "expected_days_of_cover_after": round(after_doc, 1),
        "stockout_risk": round(stockout_risk, 3),
        "lost_sales_estimate": round(lost_sales, 2),
        "service_level_target": service_level,
        "lead_time_days": lead_time,
        "store_cluster": store_cluster,
        "category": row.get("category", ""),
        "sku_type": row.get("sku_type", ""),
        "fulfillment_type": fulfillment_type,
        "vendor_id": row.get("vendor_id", ""),
        "moq_applied": moq,
        "case_pack_applied": case_pack,
    }


def _compute_display_recommendation(
    row: pd.Series,
    config: ReplenishmentConfig,
) -> dict | None:
    """Compute replenishment for display-only SKUs.

    Display dummies need fixed inventory: maintain 1-2 units on display.
    """
    on_hand = int(row.get("on_hand_qty", 0))
    in_transit = int(row.get("in_transit_qty", 0))

    if on_hand + in_transit >= config.display_min_on_hand:
        return None  # Display is covered

    qty = config.display_max_on_hand - on_hand - in_transit
    if qty <= 0:
        return None

    urgency = URGENCY_URGENT if on_hand == 0 else URGENCY_NORMAL
    urgency_rank = 1 if urgency == URGENCY_URGENT else 2

    return {
        "sku_id": row["sku_id"],
        "destination_store": row["store_id"],
        "source_location": config.default_source,
        "recommended_qty": qty,
        "urgency": urgency,
        "urgency_rank": urgency_rank,
        "reason_code": "display_replenishment",
        "reason_description": REASON_CODES["display_replenishment"],
        "on_hand_qty": on_hand,
        "in_transit_qty": in_transit,
        "reorder_point": config.display_min_on_hand,
        "safety_stock": 0.0,
        "order_up_to_level": config.display_max_on_hand,
        "avg_daily_demand": 0.0,
        "current_days_of_cover": float("inf"),
        "expected_days_of_cover_after": float("inf"),
        "stockout_risk": 1.0 if on_hand == 0 else 0.0,
        "lost_sales_estimate": 0.0,
        "service_level_target": 0.99,
        "lead_time_days": float(row.get("lead_time_days", config.default_lead_time_days)),
        "store_cluster": row.get("store_cluster", ""),
        "category": row.get("category", ""),
        "sku_type": "display_dummy",
        "fulfillment_type": "order_capture",
        "vendor_id": row.get("vendor_id", ""),
        "moq_applied": 1,
        "case_pack_applied": 1,
    }


def _determine_urgency_and_reason(
    on_hand: int,
    in_transit: int,
    current_doc: float,
    stockout_risk: float,
    config: ReplenishmentConfig,
) -> tuple[str, str]:
    """Determine urgency level and primary reason code."""
    # Emergency: currently stocked out with nothing in transit
    if on_hand == 0 and in_transit == 0:
        return URGENCY_EMERGENCY, "emergency_stockout"

    # Emergency: very high stockout probability
    if stockout_risk >= 0.9:
        return URGENCY_EMERGENCY, "projected_stockout"

    # Urgent: below emergency DOC threshold
    if current_doc < config.emergency_days_of_cover:
        return URGENCY_URGENT, "projected_stockout"

    # Urgent: high stockout risk
    if stockout_risk >= config.stockout_risk_threshold:
        return URGENCY_URGENT, "service_level_risk"

    # Urgent: below critical DOC
    if current_doc < config.critical_days_of_cover:
        return URGENCY_URGENT, "below_safety_stock"

    # Normal: standard reorder
    return URGENCY_NORMAL, "below_reorder_point"


def _empty_recommendations() -> pd.DataFrame:
    """Return empty recommendations DataFrame with correct schema."""
    return pd.DataFrame(columns=[
        "sku_id", "destination_store", "source_location", "recommended_qty",
        "urgency", "urgency_rank", "reason_code", "reason_description",
        "on_hand_qty", "in_transit_qty", "reorder_point", "safety_stock",
        "order_up_to_level", "avg_daily_demand", "current_days_of_cover",
        "expected_days_of_cover_after", "stockout_risk", "lost_sales_estimate",
        "service_level_target", "lead_time_days", "store_cluster", "category",
        "sku_type", "fulfillment_type", "vendor_id", "moq_applied", "case_pack_applied",
    ])
