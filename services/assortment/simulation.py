"""Assortment simulation utility.

Compares current heuristic assortment (top-N by sales) against the
CP-SAT optimized assortment on key metrics.

Metrics:
- Expected total score (objective value)
- Category coverage
- New-launch exposure
- Brand diversity
- Display dummy / sell-through split
- Width (unique subcategories) vs depth (avg per subcategory)

Usage:
    python -m services.assortment.simulation
"""

import argparse
import logging
from dataclasses import dataclass

import pandas as pd

from services.assortment.config import (
    AssortmentConfig,
    AssortmentScenario,
    get_scenario_for_cluster,
)
from services.assortment.scoring import compute_sku_scores

logger = logging.getLogger(__name__)


@dataclass
class SimulationMetrics:
    """Metrics for an assortment strategy."""
    strategy: str
    total_score: float
    skus_selected: int
    capacity_utilization: float
    category_mix: dict
    new_launch_pct: float
    brand_count: int
    subcategory_count: int
    display_dummy_pct: float
    avg_demand_score: float
    avg_margin_score: float
    avg_freshness_score: float
    width: int       # Unique subcategories
    depth: float     # Avg SKUs per subcategory


def heuristic_assortment(
    scored_skus: pd.DataFrame,
    display_capacity: int,
) -> pd.DataFrame:
    """Simple heuristic: top-N by demand, no constraint enforcement."""
    return scored_skus.nlargest(
        min(display_capacity, len(scored_skus)),
        "avg_weekly_demand",
    )


def optimized_assortment(
    scored_skus: pd.DataFrame,
    display_capacity: int,
    scenario: AssortmentScenario,
    config: AssortmentConfig,
    store_id: str = "SIM_STORE",
) -> pd.DataFrame:
    """CP-SAT optimized assortment."""
    from services.assortment.optimizer import optimize_store_assortment

    result = optimize_store_assortment(
        store_id=store_id,
        sku_data=scored_skus,
        display_capacity=display_capacity,
        scenario=scenario,
        config=config,
    )

    if result.selected_skus:
        selected_ids = {s["sku_id"] for s in result.selected_skus}
        return scored_skus[scored_skus["sku_id"].isin(selected_ids)]
    return pd.DataFrame()


def compute_metrics(
    selected: pd.DataFrame,
    display_capacity: int,
    strategy: str,
) -> SimulationMetrics:
    """Compute comparison metrics for an assortment selection."""
    if selected.empty:
        return SimulationMetrics(
            strategy=strategy, total_score=0, skus_selected=0,
            capacity_utilization=0, category_mix={}, new_launch_pct=0,
            brand_count=0, subcategory_count=0, display_dummy_pct=0,
            avg_demand_score=0, avg_margin_score=0, avg_freshness_score=0,
            width=0, depth=0,
        )

    n = len(selected)
    subcat_counts = selected["subcategory"].value_counts() if "subcategory" in selected.columns else pd.Series(dtype=int)

    return SimulationMetrics(
        strategy=strategy,
        total_score=float(selected.get("composite_score", pd.Series(0)).sum()),
        skus_selected=n,
        capacity_utilization=round(n / max(display_capacity, 1), 3),
        category_mix=selected["category"].value_counts().to_dict() if "category" in selected.columns else {},
        new_launch_pct=round(
            (selected["lifecycle_stage"] == "new").sum() / max(n, 1), 3
        ) if "lifecycle_stage" in selected.columns else 0,
        brand_count=int(selected["brand"].nunique()) if "brand" in selected.columns else 0,
        subcategory_count=int(selected["subcategory"].nunique()) if "subcategory" in selected.columns else 0,
        display_dummy_pct=round(
            selected["is_display_only"].sum() / max(n, 1), 3
        ) if "is_display_only" in selected.columns else 0,
        avg_demand_score=round(float(selected.get("demand_score", pd.Series(0)).mean()), 3),
        avg_margin_score=round(float(selected.get("margin_score", pd.Series(0)).mean()), 3),
        avg_freshness_score=round(float(selected.get("freshness_score", pd.Series(0)).mean()), 3),
        width=int(subcat_counts.nunique()) if not subcat_counts.empty else 0,
        depth=round(float(subcat_counts.mean()), 1) if not subcat_counts.empty else 0,
    )


def run_comparison(
    scored_skus: pd.DataFrame,
    display_capacity: int,
    scenario: AssortmentScenario,
    config: AssortmentConfig,
    store_id: str = "SIM_STORE",
) -> dict[str, SimulationMetrics]:
    """Run heuristic vs optimized comparison."""
    heuristic = heuristic_assortment(scored_skus, display_capacity)
    h_metrics = compute_metrics(heuristic, display_capacity, "heuristic")

    opt = optimized_assortment(scored_skus, display_capacity, scenario, config, store_id)
    o_metrics = compute_metrics(opt, display_capacity, "optimized")

    return {"heuristic": h_metrics, "optimized": o_metrics}


def print_comparison_report(results: dict[str, SimulationMetrics]):
    """Print formatted comparison report."""
    h = results["heuristic"]
    o = results["optimized"]

    print("=" * 70)
    print("Assortment Strategy Comparison")
    print("=" * 70)
    print(f"{'Metric':<35} {'Heuristic':>15} {'Optimized':>15}")
    print("-" * 70)

    rows = [
        ("Total Score", f"{h.total_score:.1f}", f"{o.total_score:.1f}"),
        ("SKUs Selected", str(h.skus_selected), str(o.skus_selected)),
        ("Capacity Utilization", f"{h.capacity_utilization:.1%}", f"{o.capacity_utilization:.1%}"),
        ("New Launch %", f"{h.new_launch_pct:.1%}", f"{o.new_launch_pct:.1%}"),
        ("Brand Count", str(h.brand_count), str(o.brand_count)),
        ("Subcategory Count", str(h.subcategory_count), str(o.subcategory_count)),
        ("Display Dummy %", f"{h.display_dummy_pct:.1%}", f"{o.display_dummy_pct:.1%}"),
        ("Avg Demand Score", f"{h.avg_demand_score:.3f}", f"{o.avg_demand_score:.3f}"),
        ("Avg Margin Score", f"{h.avg_margin_score:.3f}", f"{o.avg_margin_score:.3f}"),
        ("Avg Freshness Score", f"{h.avg_freshness_score:.3f}", f"{o.avg_freshness_score:.3f}"),
        ("Width (subcategories)", str(h.width), str(o.width)),
        ("Depth (avg/subcat)", f"{h.depth:.1f}", f"{o.depth:.1f}"),
    ]

    for label, hv, ov in rows:
        print(f"  {label:<33} {hv:>15} {ov:>15}")

    print("-" * 70)

    # Category mix comparison
    all_cats = set(list(h.category_mix.keys()) + list(o.category_mix.keys()))
    if all_cats:
        print("  Category Mix:")
        for cat in sorted(all_cats):
            hc = h.category_mix.get(cat, 0)
            oc = o.category_mix.get(cat, 0)
            print(f"    {cat:<29} {hc:>15} {oc:>15}")

    if h.total_score > 0:
        improvement = (o.total_score - h.total_score) / h.total_score * 100
        print(f"\n  Score improvement: {improvement:+.1f}%")

    print("=" * 70)


def generate_synthetic_skus(n_skus: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic SKU data for simulation testing."""
    import numpy as np
    rng = np.random.default_rng(seed)

    categories = ["eyeglasses"] * int(n_skus * 0.5) + \
                 ["sunglasses"] * int(n_skus * 0.3) + \
                 ["contact_lenses"] * (n_skus - int(n_skus * 0.5) - int(n_skus * 0.3))

    subcategories = rng.choice(
        ["full_rim", "half_rim", "rimless", "aviator", "round", "square", "daily", "monthly"],
        n_skus,
    )
    brands = rng.choice(["BrandA", "BrandB", "BrandC", "BrandD", "BrandE"], n_skus)
    lifecycles = rng.choice(
        ["new", "growth", "active", "mature", "aging", "eol"],
        n_skus, p=[0.1, 0.2, 0.35, 0.2, 0.1, 0.05],
    )

    return pd.DataFrame({
        "sku_id": [f"SKU_{i:04d}" for i in range(n_skus)],
        "store_id": ["SIM_STORE"] * n_skus,
        "category": categories,
        "subcategory": subcategories,
        "brand": brands,
        "sku_type": rng.choice(["display_dummy", "physical_sell"], n_skus, p=[0.7, 0.3]),
        "is_display_only": rng.choice([1, 0], n_skus, p=[0.7, 0.3]),
        "fulfillment_type": rng.choice(["order_capture", "direct_sell"], n_skus, p=[0.7, 0.3]),
        "lifecycle_stage": lifecycles,
        "mrp": rng.choice([999, 1499, 2499, 3499, 4999, 6999], n_skus),
        "margin_pct": rng.uniform(0.2, 0.6, n_skus).round(2),
        "avg_weekly_demand": rng.exponential(3, n_skus).round(1),
        "display_interest": rng.poisson(5, n_skus),
        "trial_conversion_rate": rng.uniform(0.0, 0.3, n_skus).round(3),
    })


def main():
    parser = argparse.ArgumentParser(description="Compare heuristic vs optimized assortment")
    parser.add_argument("--n-skus", type=int, default=200)
    parser.add_argument("--capacity", type=int, default=80)
    parser.add_argument("--scenario", default="metro_mass", choices=list(
        __import__("services.assortment.config", fromlist=["SCENARIOS"]).SCENARIOS.keys()
    ))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from services.assortment.config import SCENARIOS

    config = AssortmentConfig()
    scenario = SCENARIOS[args.scenario]
    skus = generate_synthetic_skus(args.n_skus)
    scored = compute_sku_scores(skus, scenario, config)

    results = run_comparison(scored, args.capacity, scenario, config)
    print_comparison_report(results)


if __name__ == "__main__":
    main()
