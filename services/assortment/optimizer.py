"""Assortment optimizer using OR-Tools CP-SAT.

Selects optimal SKU assortment per store by solving a constrained
optimization problem that maximizes expected commercial value.

Decision variables:
- x[i]: binary — whether SKU i is included in assortment
- depth[i]: integer — recommended depth for sell-through SKUs (optional)

Objective: maximize Σ score[i] × x[i]

Constraints:
- Total display capacity
- Minimum category coverage (eyeglasses, sunglasses, contact lenses)
- Maximum depth per subcategory
- Maximum per brand
- Minimum new-launch exposure
- Price tier mix
- Display dummy target split
"""

import logging
import time
from dataclasses import dataclass, field

import pandas as pd

from services.assortment.config import AssortmentConfig, AssortmentScenario

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of a single store assortment optimization."""

    store_id: str
    status: str  # optimal, feasible, infeasible, error
    objective_value: float
    solve_time_ms: float
    total_capacity: int
    used_capacity: int
    selected_skus: list[dict] = field(default_factory=list)
    excluded_skus: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def optimize_store_assortment(
    store_id: str,
    sku_data: pd.DataFrame,
    display_capacity: int,
    scenario: AssortmentScenario,
    config: AssortmentConfig,
) -> OptimizationResult:
    """Optimize assortment for a single store using CP-SAT.

    Args:
        store_id: Target store
        sku_data: Scored SKU candidates for this store (must have score_int)
        display_capacity: Number of display slots
        scenario: Scenario profile with constraint parameters
        config: Global config

    Returns:
        OptimizationResult with selected/excluded SKUs
    """
    if sku_data.empty or display_capacity <= 0:
        return OptimizationResult(
            store_id=store_id, status="infeasible",
            objective_value=0, solve_time_ms=0,
            total_capacity=display_capacity, used_capacity=0,
        )

    try:
        from ortools.sat.python import cp_model
    except ImportError:
        logger.warning("OR-Tools not available, falling back to greedy")
        return _greedy_fallback(store_id, sku_data, display_capacity, scenario)

    model = cp_model.CpModel()
    start = time.time()

    n = len(sku_data)
    skus = sku_data.reset_index(drop=True)

    # ─── Decision variables ──────────────────────────────────────────
    x = {}  # x[i] = 1 if SKU i selected
    for i in range(n):
        x[i] = model.new_bool_var(f"x_{i}")

    # ─── Objective: maximize total score ─────────────────────────────
    model.maximize(
        sum(int(skus.loc[i, "score_int"]) * x[i] for i in range(n))
    )

    # ─── Constraint 1: Display capacity ──────────────────────────────
    model.add(sum(x[i] for i in range(n)) <= display_capacity)

    # ─── Constraint 2: Category coverage ─────────────────────────────
    _add_category_constraints(model, x, skus, display_capacity, scenario)

    # ─── Constraint 3: Subcategory depth ─────────────────────────────
    _add_subcategory_depth_constraints(model, x, skus, scenario)

    # ─── Constraint 4: Brand limits ──────────────────────────────────
    _add_brand_constraints(model, x, skus, scenario)

    # ─── Constraint 5: New-launch exposure ───────────────────────────
    _add_new_launch_constraint(model, x, skus, display_capacity, scenario)

    # ─── Constraint 6: Price tier mix ────────────────────────────────
    _add_price_tier_constraints(model, x, skus, display_capacity, scenario, config)

    # ─── Constraint 7: Display dummy target ──────────────────────────
    _add_display_dummy_constraint(model, x, skus, display_capacity, scenario)

    # ─── Solve ───────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.solver_time_limit_seconds
    solver.parameters.num_workers = config.solver_num_workers

    status = solver.solve(model)
    elapsed = (time.time() - start) * 1000

    status_map = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "feasible",
        cp_model.INFEASIBLE: "infeasible",
        cp_model.MODEL_INVALID: "error",
    }
    status_str = status_map.get(status, "unknown")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        selected = []
        excluded = []
        for i in range(n):
            row = skus.iloc[i]
            rec = {
                "sku_id": row["sku_id"],
                "store_id": store_id,
                "category": row.get("category", ""),
                "subcategory": row.get("subcategory", ""),
                "brand": row.get("brand", ""),
                "sku_type": row.get("sku_type", ""),
                "is_display_only": int(row.get("is_display_only", 0)),
                "lifecycle_stage": row.get("lifecycle_stage", ""),
                "mrp": float(row.get("mrp", 0)),
                "composite_score": float(row.get("composite_score", 0)),
                "demand_score": float(row.get("demand_score", 0)),
                "margin_score": float(row.get("margin_score", 0)),
                "freshness_score": float(row.get("freshness_score", 0)),
            }
            if solver.value(x[i]):
                rec["action"] = "include"
                selected.append(rec)
            else:
                rec["action"] = "exclude"
                rec["exclusion_reason"] = _get_exclusion_reason(row, scenario)
                excluded.append(rec)

        used = len(selected)
        diagnostics = _build_diagnostics(selected, display_capacity, scenario)

        logger.info(
            f"Store {store_id}: {status_str}, "
            f"{used}/{display_capacity} slots, "
            f"obj={solver.objective_value:.0f}, "
            f"{elapsed:.0f}ms"
        )

        return OptimizationResult(
            store_id=store_id,
            status=status_str,
            objective_value=float(solver.objective_value),
            solve_time_ms=round(elapsed, 1),
            total_capacity=display_capacity,
            used_capacity=used,
            selected_skus=selected,
            excluded_skus=excluded,
            diagnostics=diagnostics,
        )

    logger.warning(f"Store {store_id}: {status_str} ({elapsed:.0f}ms)")
    return OptimizationResult(
        store_id=store_id, status=status_str,
        objective_value=0, solve_time_ms=round(elapsed, 1),
        total_capacity=display_capacity, used_capacity=0,
    )


# ─── Constraint helpers ──────────────────────────────────────────────────────


def _add_category_constraints(model, x, skus, capacity, scenario):
    """Minimum category coverage."""
    for cat, min_pct in [
        ("eyeglasses", scenario.min_eyeglasses_pct),
        ("sunglasses", scenario.min_sunglasses_pct),
        ("contact_lenses", scenario.min_contact_lenses_pct),
    ]:
        indices = skus.index[skus["category"] == cat].tolist()
        if indices:
            min_count = max(1, int(capacity * min_pct))
            model.add(sum(x[i] for i in indices) >= min(min_count, len(indices)))


def _add_subcategory_depth_constraints(model, x, skus, scenario):
    """Maximum SKUs per subcategory."""
    if "subcategory" not in skus.columns:
        return
    for subcat in skus["subcategory"].dropna().unique():
        indices = skus.index[skus["subcategory"] == subcat].tolist()
        if len(indices) > scenario.max_depth_per_subcategory:
            model.add(
                sum(x[i] for i in indices) <= scenario.max_depth_per_subcategory
            )


def _add_brand_constraints(model, x, skus, scenario):
    """Maximum SKUs per brand."""
    if "brand" not in skus.columns:
        return
    for brand in skus["brand"].dropna().unique():
        indices = skus.index[skus["brand"] == brand].tolist()
        if len(indices) > scenario.max_per_brand:
            model.add(sum(x[i] for i in indices) <= scenario.max_per_brand)


def _add_new_launch_constraint(model, x, skus, capacity, scenario):
    """Minimum new-launch SKUs."""
    new_indices = skus.index[
        skus["lifecycle_stage"] == scenario.new_launch_lifecycle
    ].tolist()
    if new_indices:
        min_new = max(1, int(capacity * scenario.min_new_launch_pct))
        model.add(sum(x[i] for i in new_indices) >= min(min_new, len(new_indices)))


def _add_price_tier_constraints(model, x, skus, capacity, scenario, config):
    """Minimum price tier representation."""
    if "mrp" not in skus.columns:
        return
    for tier, (lo, hi) in config.price_tiers.items():
        min_pct = getattr(scenario, f"min_{tier}_pct", 0)
        if min_pct > 0:
            indices = skus.index[
                (skus["mrp"] >= lo) & (skus["mrp"] < hi)
            ].tolist()
            if indices:
                min_count = max(1, int(capacity * min_pct))
                model.add(sum(x[i] for i in indices) >= min(min_count, len(indices)))


def _add_display_dummy_constraint(model, x, skus, capacity, scenario):
    """Target split between display dummies and sell-through."""
    dummy_indices = skus.index[skus["is_display_only"] == 1].tolist()
    if dummy_indices and capacity > 0:
        target = int(capacity * scenario.display_dummy_target_pct)
        # Allow ±10% flexibility
        lo = max(0, target - int(capacity * 0.10))
        hi = min(len(dummy_indices), target + int(capacity * 0.10))
        model.add(sum(x[i] for i in dummy_indices) >= lo)
        model.add(sum(x[i] for i in dummy_indices) <= hi)


# ─── Diagnostics ─────────────────────────────────────────────────────────────


def _build_diagnostics(selected: list[dict], capacity: int, scenario: AssortmentScenario) -> dict:
    """Build diagnostic summary for the optimization result."""
    if not selected:
        return {}

    df = pd.DataFrame(selected)
    diag = {
        "capacity_utilization": round(len(df) / max(capacity, 1), 3),
        "category_mix": df["category"].value_counts().to_dict() if "category" in df else {},
        "lifecycle_mix": df["lifecycle_stage"].value_counts().to_dict() if "lifecycle_stage" in df else {},
        "display_dummy_pct": round(
            df["is_display_only"].sum() / max(len(df), 1), 3
        ) if "is_display_only" in df else 0,
        "avg_composite_score": round(df["composite_score"].mean(), 3),
        "brand_count": int(df["brand"].nunique()) if "brand" in df else 0,
        "subcategory_count": int(df["subcategory"].nunique()) if "subcategory" in df else 0,
    }

    # New launch count
    if "lifecycle_stage" in df.columns:
        diag["new_launch_count"] = int(
            (df["lifecycle_stage"] == scenario.new_launch_lifecycle).sum()
        )
        diag["new_launch_pct"] = round(
            diag["new_launch_count"] / max(len(df), 1), 3
        )

    return diag


def _get_exclusion_reason(row: pd.Series, scenario: AssortmentScenario) -> str:
    """Determine why a SKU was excluded."""
    score = row.get("composite_score", 0)
    if score <= 0:
        return "zero_or_negative_score"
    if row.get("lifecycle_stage") == "eol":
        return "end_of_life"
    if row.get("lifecycle_stage") == "aging":
        return "aging_product"
    if float(row.get("avg_weekly_demand", 0)) <= 0 and not row.get("is_display_only"):
        return "no_demand"
    return "capacity_or_constraint_limit"


# ─── Greedy fallback ─────────────────────────────────────────────────────────


def _greedy_fallback(
    store_id: str,
    sku_data: pd.DataFrame,
    display_capacity: int,
    scenario: AssortmentScenario,
) -> OptimizationResult:
    """Greedy heuristic when OR-Tools is not available."""
    sorted_df = sku_data.sort_values("composite_score", ascending=False)

    selected = []
    excluded = []
    for i, (_, row) in enumerate(sorted_df.iterrows()):
        rec = {
            "sku_id": row["sku_id"],
            "store_id": store_id,
            "category": row.get("category", ""),
            "subcategory": row.get("subcategory", ""),
            "brand": row.get("brand", ""),
            "sku_type": row.get("sku_type", ""),
            "is_display_only": int(row.get("is_display_only", 0)),
            "lifecycle_stage": row.get("lifecycle_stage", ""),
            "mrp": float(row.get("mrp", 0)),
            "composite_score": float(row.get("composite_score", 0)),
            "demand_score": float(row.get("demand_score", 0)),
            "margin_score": float(row.get("margin_score", 0)),
            "freshness_score": float(row.get("freshness_score", 0)),
        }
        if len(selected) < display_capacity:
            rec["action"] = "include"
            selected.append(rec)
        else:
            rec["action"] = "exclude"
            rec["exclusion_reason"] = "capacity_or_constraint_limit"
            excluded.append(rec)

    return OptimizationResult(
        store_id=store_id,
        status="greedy_fallback",
        objective_value=sum(s["composite_score"] for s in selected),
        solve_time_ms=0,
        total_capacity=display_capacity,
        used_capacity=len(selected),
        selected_skus=selected,
        excluded_skus=excluded,
        diagnostics=_build_diagnostics(selected, display_capacity, scenario),
    )


def generate_assortment_changes(
    current_display: pd.DataFrame,
    recommended: list[dict],
) -> pd.DataFrame:
    """Diff current vs recommended display to produce actionable changes."""
    current_set = set(zip(current_display["store_id"], current_display["sku_id"]))
    rec_df = pd.DataFrame(recommended)
    if rec_df.empty:
        return pd.DataFrame(columns=["store_id", "sku_id", "action"])
    recommended_set = set(zip(rec_df["store_id"], rec_df["sku_id"]))

    changes = []
    for store_id, sku_id in recommended_set - current_set:
        changes.append({"store_id": store_id, "sku_id": sku_id, "action": "add_to_display"})
    for store_id, sku_id in current_set - recommended_set:
        changes.append({"store_id": store_id, "sku_id": sku_id, "action": "remove_from_display"})

    return pd.DataFrame(changes) if changes else pd.DataFrame(columns=["store_id", "sku_id", "action"])
