"""Replenishment simulation utility.

Compares current-state (weekly manual) replenishment vs daily automated
replenishment over a historical period.

Metrics:
- Service level (fill rate)
- Average days of cover
- Stockout rate
- Total units ordered
- Inventory carrying cost
- Lost sales estimate

Usage:
    python -m services.replenishment.simulation
    python -m services.replenishment.simulation --weeks 12
"""

import argparse
import logging
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from services.replenishment.config import ReplenishmentConfig
from services.replenishment.engine import (
    compute_order_up_to_level,
    compute_reorder_point,
    compute_safety_stock,
    get_z_score,
    round_up_to_case_pack,
)

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Results from a replenishment simulation run."""
    strategy: str
    total_days: int
    avg_service_level: float
    avg_fill_rate: float
    stockout_days: int
    stockout_rate: float
    total_units_ordered: int
    total_orders_placed: int
    avg_days_of_cover: float
    avg_on_hand: float
    total_lost_sales_units: float
    total_carrying_cost: float


@dataclass
class SimulationConfig:
    """Configuration for replenishment simulation."""
    n_weeks: int = 12
    carrying_cost_per_unit_day: float = 0.5  # ₹ per unit per day
    lost_sale_cost_per_unit: float = 500.0   # ₹ per lost unit
    review_period_weekly: int = 7  # Days between reviews for weekly strategy
    review_period_daily: int = 1   # Days between reviews for daily strategy
    lead_time_days: int = 7
    service_level: float = 0.95
    moq: int = 1
    case_pack: int = 1
    initial_stock: int = 50


def simulate_single_series(
    demand: np.ndarray,
    review_period: int,
    lead_time: int,
    service_level: float,
    config: SimulationConfig,
    replenishment_config: ReplenishmentConfig | None = None,
) -> SimulationResult:
    """Simulate replenishment for a single demand series.

    Args:
        demand: Daily demand array
        review_period: Days between replenishment reviews
        lead_time: Delivery lead time in days
        service_level: Target service level
        config: Simulation configuration

    Returns:
        SimulationResult with performance metrics
    """
    if replenishment_config is None:
        replenishment_config = ReplenishmentConfig()

    n_days = len(demand)
    on_hand = config.initial_stock
    in_transit = 0
    pending_orders = []  # (arrival_day, qty)

    # Compute demand stats
    avg_daily = float(demand.mean())
    std_daily = float(demand.std()) if len(demand) > 1 else 0.0

    z = get_z_score(service_level, replenishment_config)
    safety = compute_safety_stock(std_daily, lead_time, z)
    rop = compute_reorder_point(avg_daily, lead_time, safety)
    out_level = compute_order_up_to_level(
        avg_daily,
        max(review_period + lead_time, 14),  # Cover review + lead time
        safety,
    )

    # Tracking
    stockout_days = 0
    total_ordered = 0
    total_orders = 0
    lost_sales_units = 0.0
    carrying_cost = 0.0
    units_demanded = 0
    units_fulfilled = 0
    doc_records = []

    for day in range(n_days):
        # Receive pending orders
        new_pending = []
        for arrival_day, qty in pending_orders:
            if day >= arrival_day:
                on_hand += qty
                in_transit -= qty
            else:
                new_pending.append((arrival_day, qty))
        pending_orders = new_pending

        # Fulfill demand
        day_demand = int(demand[day])
        units_demanded += day_demand
        fulfilled = min(day_demand, on_hand)
        units_fulfilled += fulfilled
        on_hand -= fulfilled

        lost = day_demand - fulfilled
        lost_sales_units += lost

        if on_hand == 0 and day_demand > 0:
            stockout_days += 1

        # Carrying cost
        carrying_cost += on_hand * config.carrying_cost_per_unit_day

        # Days of cover
        if avg_daily > 0:
            doc_records.append((on_hand + in_transit) / avg_daily)
        else:
            doc_records.append(float("inf") if on_hand > 0 else 0)

        # Review and order
        if day % review_period == 0:
            available = on_hand + in_transit
            if available <= rop:
                raw_qty = max(0, out_level - available)
                qty = round_up_to_case_pack(raw_qty, config.case_pack)
                qty = max(qty, config.moq) if qty > 0 else 0
                if qty > 0:
                    pending_orders.append((day + lead_time, qty))
                    in_transit += qty
                    total_ordered += qty
                    total_orders += 1

    fill_rate = units_fulfilled / units_demanded if units_demanded > 0 else 1.0
    service_lvl = 1.0 - (stockout_days / n_days) if n_days > 0 else 1.0
    doc_array = [d for d in doc_records if d != float("inf")]
    avg_doc = float(np.mean(doc_array)) if doc_array else 0.0

    strategy = "daily" if review_period == 1 else f"weekly_{review_period}d"

    return SimulationResult(
        strategy=strategy,
        total_days=n_days,
        avg_service_level=round(service_lvl, 4),
        avg_fill_rate=round(fill_rate, 4),
        stockout_days=stockout_days,
        stockout_rate=round(stockout_days / n_days if n_days > 0 else 0, 4),
        total_units_ordered=total_ordered,
        total_orders_placed=total_orders,
        avg_days_of_cover=round(avg_doc, 1),
        avg_on_hand=round(carrying_cost / (n_days * config.carrying_cost_per_unit_day) if n_days > 0 else 0, 1),
        total_lost_sales_units=round(lost_sales_units, 1),
        total_carrying_cost=round(carrying_cost, 2),
    )


def run_comparison_simulation(
    demand: np.ndarray,
    config: SimulationConfig | None = None,
) -> dict[str, SimulationResult]:
    """Compare weekly manual vs daily automated replenishment.

    Returns dict with 'weekly' and 'daily' SimulationResult objects.
    """
    if config is None:
        config = SimulationConfig()

    replenishment_config = ReplenishmentConfig()

    weekly_result = simulate_single_series(
        demand=demand,
        review_period=config.review_period_weekly,
        lead_time=config.lead_time_days,
        service_level=config.service_level,
        config=config,
        replenishment_config=replenishment_config,
    )

    daily_result = simulate_single_series(
        demand=demand,
        review_period=config.review_period_daily,
        lead_time=config.lead_time_days,
        service_level=config.service_level,
        config=config,
        replenishment_config=replenishment_config,
    )

    return {"weekly": weekly_result, "daily": daily_result}


def generate_synthetic_demand(
    n_days: int = 84,
    base_demand: float = 5.0,
    seasonality_amplitude: float = 2.0,
    noise_std: float = 1.5,
    seed: int = 42,
) -> np.ndarray:
    """Generate synthetic daily demand for simulation testing."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_days)
    seasonal = seasonality_amplitude * np.sin(2 * np.pi * t / 7)  # Weekly pattern
    trend = 0.01 * t  # Slight upward trend
    noise = rng.normal(0, noise_std, n_days)
    demand = base_demand + seasonal + trend + noise
    return np.maximum(demand, 0).astype(int)


def print_comparison_report(results: dict[str, SimulationResult]):
    """Print a formatted comparison report."""
    print("=" * 70)
    print("Replenishment Strategy Comparison")
    print("=" * 70)
    print(f"{'Metric':<35} {'Weekly':>15} {'Daily':>15}")
    print("-" * 70)

    w = results["weekly"]
    d = results["daily"]

    rows = [
        ("Fill Rate", f"{w.avg_fill_rate:.1%}", f"{d.avg_fill_rate:.1%}"),
        ("Service Level (no-stockout %)", f"{w.avg_service_level:.1%}", f"{d.avg_service_level:.1%}"),
        ("Stockout Days", str(w.stockout_days), str(d.stockout_days)),
        ("Stockout Rate", f"{w.stockout_rate:.1%}", f"{d.stockout_rate:.1%}"),
        ("Avg Days of Cover", f"{w.avg_days_of_cover:.1f}", f"{d.avg_days_of_cover:.1f}"),
        ("Avg On-Hand Units", f"{w.avg_on_hand:.1f}", f"{d.avg_on_hand:.1f}"),
        ("Total Units Ordered", f"{w.total_units_ordered:,}", f"{d.total_units_ordered:,}"),
        ("Orders Placed", str(w.total_orders_placed), str(d.total_orders_placed)),
        ("Lost Sales (units)", f"{w.total_lost_sales_units:.0f}", f"{d.total_lost_sales_units:.0f}"),
        ("Carrying Cost", f"₹{w.total_carrying_cost:,.0f}", f"₹{d.total_carrying_cost:,.0f}"),
    ]

    for label, wv, dv in rows:
        print(f"  {label:<33} {wv:>15} {dv:>15}")

    print("-" * 70)

    # Improvement summary
    if w.stockout_days > 0:
        stockout_improvement = (w.stockout_days - d.stockout_days) / w.stockout_days * 100
        print(f"  Stockout reduction: {stockout_improvement:.0f}%")
    if w.total_carrying_cost > 0:
        cost_change = (d.total_carrying_cost - w.total_carrying_cost) / w.total_carrying_cost * 100
        print(f"  Carrying cost change: {cost_change:+.1f}%")
    if w.total_lost_sales_units > 0:
        lost_improvement = (w.total_lost_sales_units - d.total_lost_sales_units) / w.total_lost_sales_units * 100
        print(f"  Lost sales reduction: {lost_improvement:.0f}%")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Simulate weekly vs daily replenishment")
    parser.add_argument("--weeks", type=int, default=12)
    parser.add_argument("--base-demand", type=float, default=5.0)
    parser.add_argument("--lead-time", type=int, default=7)
    parser.add_argument("--service-level", type=float, default=0.95)
    parser.add_argument("--initial-stock", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sim_config = SimulationConfig(
        n_weeks=args.weeks,
        lead_time_days=args.lead_time,
        service_level=args.service_level,
        initial_stock=args.initial_stock,
    )

    demand = generate_synthetic_demand(
        n_days=args.weeks * 7,
        base_demand=args.base_demand,
    )

    logger.info(f"Simulating {args.weeks} weeks ({len(demand)} days)")
    logger.info(f"Avg daily demand: {demand.mean():.1f}, Std: {demand.std():.1f}")

    results = run_comparison_simulation(demand, sim_config)
    print_comparison_report(results)


if __name__ == "__main__":
    main()
