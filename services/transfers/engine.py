"""Inter-store transfer optimization engine.

Identifies and optimizes inter-store transfers to rebalance inventory:
- Excess / stranded / aging stock at source stores → high-demand destinations
- Maximizes recovered sales net of transfer cost
- Respects source presentation stock, destination capacity, transfer lanes

Pipeline:
1. Candidate generation — match excess sources with deficit destinations
2. Scoring — estimate recovered demand value and transfer cost
3. Optimization — OR-Tools MIP to select best transfers subject to constraints
4. Output — ranked transfer recommendations with expected impact

Decision variables:
  x[i] ∈ {0,1}  — whether candidate transfer i is selected
  q[i] ∈ [1, max_qty] — quantity to transfer (integer)

Objective:
  maximize Σ  (unit_value[i] × q[i] - variable_cost[i] × q[i] - fixed_cost[i] × x[i])
            × priority_bonus[i]

Constraints:
  - Source stock after all outbound transfers ≥ min_presentation_stock
  - Destination stock after all inbound transfers ≤ capacity × max_utilization
  - At most max_transfers_per_source outbound per source store
  - At most max_transfers_per_destination inbound per destination store
  - Total outbound units per source ≤ max_units_per_source
  - q[i] ≤ transferable_qty[i] (can't transfer more than available excess)
  - q[i] ≥ min_transfer_qty × x[i]
  - q[i] ≤ max_transfer_qty × x[i]
"""

import logging
import time
from dataclasses import dataclass, field

import pandas as pd

from services.transfers.config import (
    REASON_AGING_CLEARANCE,
    REASON_EOL_CLEARANCE,
    REASON_REBALANCE,
    REASON_STOCKOUT_PREVENTION,
    TransferConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class TransferResult:
    """Result of a transfer optimization run."""

    status: str  # optimal, feasible, infeasible, no_candidates, error
    solve_time_ms: float
    total_candidates: int
    selected_transfers: int
    total_units: int
    total_recovered_value: float
    total_transfer_cost: float
    net_value: float
    transfers: list[dict] = field(default_factory=list)
    source_relief: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)


# ─── Candidate generation ────────────────────────────────────────────────────


def generate_candidates(
    positions: pd.DataFrame,
    config: TransferConfig,
) -> pd.DataFrame:
    """Generate transfer candidates by matching excess sources with deficit destinations.

    A source qualifies if:
      - weeks_of_supply ≥ min_source_wos
      - lifecycle_stage in eligible stages
      - on_hand_qty > min_presentation_stock

    A destination qualifies if:
      - weeks_of_supply ≤ max_destination_wos
      - forecast_weekly ≥ min_destination_demand
      - has capacity headroom

    Returns DataFrame of candidate transfers with scoring columns.
    """
    if positions.empty:
        return pd.DataFrame()

    # Identify sources (excess inventory)
    sources = positions[
        (positions["weeks_of_supply"] >= config.min_source_wos)
        & (positions["lifecycle_stage"].isin(config.eligible_lifecycle_stages))
        & (positions["on_hand_qty"] > config.min_presentation_stock)
    ].copy()

    if sources.empty:
        logger.info("No excess source positions found")
        return pd.DataFrame()

    # Compute transferable quantity (what can leave the source)
    sources["transferable_qty"] = (
        sources["on_hand_qty"] - config.min_presentation_stock
    ).clip(lower=0)
    sources = sources[sources["transferable_qty"] >= config.min_transfer_qty]

    # Identify destinations (deficit inventory)
    destinations = positions[
        (positions["weeks_of_supply"] <= config.max_destination_wos)
        & (positions["forecast_weekly"] >= config.min_destination_demand)
    ].copy()

    if destinations.empty:
        logger.info("No deficit destination positions found")
        return pd.DataFrame()

    # Compute destination headroom
    destinations["capacity_headroom"] = (
        destinations["total_capacity"] * config.max_destination_capacity_pct
        - destinations["current_store_units"]
    ).clip(lower=0)
    destinations = destinations[destinations["capacity_headroom"] > 0]

    # Match by SKU (cross join sources × destinations for same SKU)
    candidates = sources.merge(
        destinations,
        on="sku_id",
        suffixes=("_src", "_dst"),
        how="inner",
    )

    # Don't transfer to same store
    candidates = candidates[candidates["store_id_src"] != candidates["store_id_dst"]]

    if candidates.empty:
        logger.info("No matching source-destination pairs")
        return pd.DataFrame()

    # Compute transfer lead time based on region
    candidates["transfer_lead_time"] = candidates.apply(
        lambda r: _get_transfer_lead_time(
            r.get("region_src", ""),
            r.get("region_dst", ""),
            config,
        ),
        axis=1,
    )

    # Filter by max acceptable lead time
    candidates = candidates[
        candidates["transfer_lead_time"] <= config.max_transfer_lead_time_days
    ]

    # Compute max transferable quantity per candidate
    candidates["max_qty"] = candidates.apply(
        lambda r: min(
            int(r["transferable_qty"]),
            int(r["capacity_headroom"]),
            config.max_transfer_qty,
        ),
        axis=1,
    )
    candidates = candidates[candidates["max_qty"] >= config.min_transfer_qty]

    # Score each candidate
    candidates = _score_candidates(candidates, config)

    logger.info(
        f"Generated {len(candidates)} transfer candidates "
        f"({sources['store_id'].nunique()} source stores, "
        f"{destinations['store_id'].nunique()} destination stores)"
    )

    return candidates


def _get_transfer_lead_time(
    src_region: str, dst_region: str, config: TransferConfig
) -> int:
    """Determine transfer lead time based on regions."""
    if not src_region or not dst_region:
        return config.default_transfer_lead_time_days
    if src_region == dst_region:
        return config.same_region_lead_time_days
    return config.cross_region_lead_time_days


def _score_candidates(
    candidates: pd.DataFrame, config: TransferConfig
) -> pd.DataFrame:
    """Score each candidate transfer on recovered value, cost, and priority."""
    df = candidates.copy()

    # Demand at destination (weekly) × planning horizon = recoverable demand
    df["demand_during_horizon"] = (
        df["forecast_weekly_dst"] * config.planning_horizon_weeks
    )

    # Deficit units at destination (how much they need)
    df["deficit_qty"] = (
        df["demand_during_horizon"] - df["available_qty_dst"]
    ).clip(lower=0).astype(int)

    # Suggested quantity = min(max_qty, deficit_qty), at least min_transfer_qty
    df["suggested_qty"] = df[["max_qty", "deficit_qty"]].min(axis=1).clip(
        lower=config.min_transfer_qty
    )

    # Unit value — use avg weekly demand × default price as proxy for MRP
    df["unit_value"] = config.default_unit_price

    # Recovered sales value = suggested_qty × unit_value × fill_rate
    # fill_rate: fraction of deficit being covered
    df["fill_rate"] = (
        df["suggested_qty"] / df["demand_during_horizon"].clip(lower=1)
    ).clip(upper=1.0)
    df["recovered_value"] = df["suggested_qty"] * df["unit_value"] * df["fill_rate"]

    # Transfer cost = variable + fixed
    df["variable_cost"] = df["suggested_qty"] * config.cost_per_unit
    df["fixed_cost"] = config.fixed_cost_per_transfer
    df["total_cost"] = df["variable_cost"] + df["fixed_cost"]

    # Net value
    df["net_value"] = df["recovered_value"] - df["total_cost"]

    # Priority bonus for aging/EOL stock
    df["priority_bonus"] = 1.0
    df.loc[
        df["lifecycle_stage_src"] == "aging", "priority_bonus"
    ] = config.aging_bonus_multiplier
    df.loc[
        df["lifecycle_stage_src"] == "eol", "priority_bonus"
    ] = config.eol_bonus_multiplier

    # Weighted net value (objective coefficient)
    df["weighted_value"] = df["net_value"] * df["priority_bonus"]

    # Reason code
    df["reason"] = df.apply(_determine_reason, axis=1)

    # Filter out candidates with negative net value
    df = df[df["net_value"] >= config.min_net_value]

    return df.sort_values("weighted_value", ascending=False).reset_index(drop=True)


def _determine_reason(row: pd.Series) -> str:
    """Determine transfer reason based on source and destination state."""
    if row.get("lifecycle_stage_src") == "eol":
        return REASON_EOL_CLEARANCE
    if row.get("lifecycle_stage_src") == "aging":
        return REASON_AGING_CLEARANCE
    if row.get("weeks_of_supply_dst", 99) <= 1.0:
        return REASON_STOCKOUT_PREVENTION
    return REASON_REBALANCE


# ─── OR-Tools optimization ───────────────────────────────────────────────────


def optimize_transfers(
    candidates: pd.DataFrame,
    config: TransferConfig,
) -> TransferResult:
    """Solve the transfer selection problem using OR-Tools MIP.

    Selects the optimal set of transfers to maximize net recovered value
    subject to source, destination, and operational constraints.
    """
    if candidates.empty:
        return TransferResult(
            status="no_candidates", solve_time_ms=0,
            total_candidates=0, selected_transfers=0,
            total_units=0, total_recovered_value=0,
            total_transfer_cost=0, net_value=0,
        )

    try:
        from ortools.linear_solver import pywraplp
    except ImportError:
        logger.warning("OR-Tools not available, falling back to greedy")
        return _greedy_fallback(candidates, config)

    start = time.time()
    n = len(candidates)

    solver = pywraplp.Solver.CreateSolver("SCIP")
    if not solver:
        logger.warning("SCIP solver not available, falling back to greedy")
        return _greedy_fallback(candidates, config)

    solver.set_time_limit(config.solver_time_limit_seconds * 1000)

    # ─── Decision variables ──────────────────────────────────────────
    x = {}  # x[i] = 1 if transfer i is selected
    q = {}  # q[i] = quantity to transfer

    for i in range(n):
        x[i] = solver.IntVar(0, 1, f"x_{i}")
        max_qty = int(candidates.iloc[i]["max_qty"])
        q[i] = solver.IntVar(0, max_qty, f"q_{i}")

    # ─── Link x and q: q[i] > 0 iff x[i] = 1 ───────────────────────
    for i in range(n):
        max_qty = int(candidates.iloc[i]["max_qty"])
        solver.Add(q[i] >= config.min_transfer_qty * x[i])
        solver.Add(q[i] <= max_qty * x[i])

    # ─── Constraint: Source store outbound limits ────────────────────
    source_stores = candidates["store_id_src"].unique()
    for store in source_stores:
        indices = candidates.index[candidates["store_id_src"] == store].tolist()

        # Max transfers per source
        solver.Add(
            sum(x[i] for i in indices) <= config.max_transfers_per_source
        )

        # Max total units from source
        solver.Add(
            sum(q[i] for i in indices) <= config.max_units_per_source
        )

        # Don't exceed transferable stock per SKU at this source
        for sku_id in candidates.loc[indices, "sku_id"].unique():
            sku_indices = candidates.index[
                (candidates["store_id_src"] == store)
                & (candidates["sku_id"] == sku_id)
            ].tolist()
            transferable = int(
                candidates.loc[sku_indices[0], "transferable_qty"]
            )
            solver.Add(sum(q[i] for i in sku_indices) <= transferable)

    # ─── Constraint: Destination store inbound limits ────────────────
    dest_stores = candidates["store_id_dst"].unique()
    for store in dest_stores:
        indices = candidates.index[candidates["store_id_dst"] == store].tolist()

        # Max transfers per destination
        solver.Add(
            sum(x[i] for i in indices) <= config.max_transfers_per_destination
        )

        # Don't exceed capacity headroom
        headroom = int(candidates.loc[indices[0], "capacity_headroom"])
        solver.Add(sum(q[i] for i in indices) <= headroom)

    # ─── Objective: maximize net recovered value ─────────────────────
    objective = solver.Objective()
    for i in range(n):
        row = candidates.iloc[i]
        # Per-unit net value × priority bonus
        unit_net = float(row["unit_value"] * row["fill_rate"] - config.cost_per_unit)
        bonus = float(row["priority_bonus"])
        # q coefficient = unit_net × bonus
        objective.SetCoefficient(q[i], unit_net * bonus)
        # x coefficient = -fixed_cost × bonus (fixed cost per transfer)
        objective.SetCoefficient(x[i], -config.fixed_cost_per_transfer * bonus)

    objective.SetMaximization()

    # ─── Solve ───────────────────────────────────────────────────────
    status = solver.Solve()
    elapsed = (time.time() - start) * 1000

    status_map = {
        pywraplp.Solver.OPTIMAL: "optimal",
        pywraplp.Solver.FEASIBLE: "feasible",
        pywraplp.Solver.INFEASIBLE: "infeasible",
        pywraplp.Solver.UNBOUNDED: "error",
        pywraplp.Solver.NOT_SOLVED: "error",
    }
    status_str = status_map.get(status, "unknown")

    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        logger.warning(f"Transfer optimization: {status_str} ({elapsed:.0f}ms)")
        return TransferResult(
            status=status_str, solve_time_ms=round(elapsed, 1),
            total_candidates=n, selected_transfers=0,
            total_units=0, total_recovered_value=0,
            total_transfer_cost=0, net_value=0,
        )

    # ─── Extract solution ────────────────────────────────────────────
    transfers = []
    total_units = 0
    total_recovered = 0.0
    total_cost = 0.0
    source_relief = {}

    for i in range(n):
        if x[i].solution_value() > 0.5:
            row = candidates.iloc[i]
            qty = int(round(q[i].solution_value()))
            if qty <= 0:
                continue

            unit_val = float(row["unit_value"])
            fill = float(row["fill_rate"])
            recovered = qty * unit_val * fill
            cost = qty * config.cost_per_unit + config.fixed_cost_per_transfer
            net = recovered - cost

            transfer = {
                "transfer_id": f"TRF-{row['store_id_src']}-{row['store_id_dst']}-{row['sku_id']}",
                "sku_id": row["sku_id"],
                "from_store_id": row["store_id_src"],
                "to_store_id": row["store_id_dst"],
                "qty": qty,
                "reason": row["reason"],
                "transfer_lead_time_days": int(row["transfer_lead_time"]),
                "source_wos_before": round(float(row["weeks_of_supply_src"]), 1),
                "destination_wos_before": round(float(row["weeks_of_supply_dst"]), 1),
                "recovered_value": round(recovered, 2),
                "transfer_cost": round(cost, 2),
                "net_value": round(net, 2),
                "lifecycle_stage": row.get("lifecycle_stage_src", ""),
                "category": row.get("category_src", ""),
                "from_region": row.get("region_src", ""),
                "to_region": row.get("region_dst", ""),
                "priority_bonus": float(row["priority_bonus"]),
            }
            transfers.append(transfer)
            total_units += qty
            total_recovered += recovered
            total_cost += cost

            # Track source relief
            src = row["store_id_src"]
            if src not in source_relief:
                source_relief[src] = {"units_out": 0, "skus_out": 0, "aging_cleared": 0}
            source_relief[src]["units_out"] += qty
            source_relief[src]["skus_out"] += 1
            if row.get("lifecycle_stage_src") in ("aging", "eol"):
                source_relief[src]["aging_cleared"] += qty

    net_value = total_recovered - total_cost

    diagnostics = _build_diagnostics(transfers, candidates, elapsed)

    logger.info(
        f"Transfer optimization: {status_str}, "
        f"{len(transfers)}/{n} candidates selected, "
        f"{total_units} units, net ₹{net_value:,.0f} ({elapsed:.0f}ms)"
    )

    return TransferResult(
        status=status_str,
        solve_time_ms=round(elapsed, 1),
        total_candidates=n,
        selected_transfers=len(transfers),
        total_units=total_units,
        total_recovered_value=round(total_recovered, 2),
        total_transfer_cost=round(total_cost, 2),
        net_value=round(net_value, 2),
        transfers=transfers,
        source_relief=source_relief,
        diagnostics=diagnostics,
    )


# ─── Greedy fallback ─────────────────────────────────────────────────────────


def _greedy_fallback(
    candidates: pd.DataFrame,
    config: TransferConfig,
) -> TransferResult:
    """Greedy heuristic when OR-Tools is not available.

    Selects candidates in order of weighted_value, respecting constraints.
    """
    start = time.time()
    sorted_df = candidates.sort_values("weighted_value", ascending=False)

    source_counts = {}  # store_id -> transfer count
    source_units = {}   # store_id -> total units out
    source_sku_units = {}  # (store_id, sku_id) -> units out
    dest_counts = {}    # store_id -> transfer count
    dest_units = {}     # store_id -> total units in

    transfers = []
    total_units = 0
    total_recovered = 0.0
    total_cost = 0.0
    source_relief = {}

    for _, row in sorted_df.iterrows():
        src = row["store_id_src"]
        dst = row["store_id_dst"]
        sku = row["sku_id"]

        # Check source constraints
        if source_counts.get(src, 0) >= config.max_transfers_per_source:
            continue
        if source_units.get(src, 0) >= config.max_units_per_source:
            continue

        # Check destination constraints
        if dest_counts.get(dst, 0) >= config.max_transfers_per_destination:
            continue
        headroom = int(row["capacity_headroom"])
        if dest_units.get(dst, 0) >= headroom:
            continue

        # Check SKU-level transferable qty
        transferable = int(row["transferable_qty"])
        already_out = source_sku_units.get((src, sku), 0)
        remaining = transferable - already_out
        if remaining < config.min_transfer_qty:
            continue

        qty = min(
            int(row["suggested_qty"]),
            remaining,
            headroom - dest_units.get(dst, 0),
            config.max_transfer_qty,
            config.max_units_per_source - source_units.get(src, 0),
        )
        if qty < config.min_transfer_qty:
            continue

        unit_val = float(row["unit_value"])
        fill = float(row["fill_rate"])
        recovered = qty * unit_val * fill
        cost = qty * config.cost_per_unit + config.fixed_cost_per_transfer
        net = recovered - cost

        if net < config.min_net_value:
            continue

        transfer = {
            "transfer_id": f"TRF-{src}-{dst}-{sku}",
            "sku_id": sku,
            "from_store_id": src,
            "to_store_id": dst,
            "qty": qty,
            "reason": row["reason"],
            "transfer_lead_time_days": int(row["transfer_lead_time"]),
            "source_wos_before": round(float(row["weeks_of_supply_src"]), 1),
            "destination_wos_before": round(float(row["weeks_of_supply_dst"]), 1),
            "recovered_value": round(recovered, 2),
            "transfer_cost": round(cost, 2),
            "net_value": round(net, 2),
            "lifecycle_stage": row.get("lifecycle_stage_src", ""),
            "category": row.get("category_src", ""),
            "from_region": row.get("region_src", ""),
            "to_region": row.get("region_dst", ""),
            "priority_bonus": float(row["priority_bonus"]),
        }
        transfers.append(transfer)

        # Update tracking
        source_counts[src] = source_counts.get(src, 0) + 1
        source_units[src] = source_units.get(src, 0) + qty
        source_sku_units[(src, sku)] = already_out + qty
        dest_counts[dst] = dest_counts.get(dst, 0) + 1
        dest_units[dst] = dest_units.get(dst, 0) + qty
        total_units += qty
        total_recovered += recovered
        total_cost += cost

        if src not in source_relief:
            source_relief[src] = {"units_out": 0, "skus_out": 0, "aging_cleared": 0}
        source_relief[src]["units_out"] += qty
        source_relief[src]["skus_out"] += 1
        if row.get("lifecycle_stage_src") in ("aging", "eol"):
            source_relief[src]["aging_cleared"] += qty

    elapsed = (time.time() - start) * 1000
    net_value = total_recovered - total_cost
    diagnostics = _build_diagnostics(transfers, candidates, elapsed)

    logger.info(
        f"Transfer greedy: {len(transfers)}/{len(candidates)} selected, "
        f"{total_units} units, net ₹{net_value:,.0f} ({elapsed:.0f}ms)"
    )

    return TransferResult(
        status="greedy_fallback",
        solve_time_ms=round(elapsed, 1),
        total_candidates=len(candidates),
        selected_transfers=len(transfers),
        total_units=total_units,
        total_recovered_value=round(total_recovered, 2),
        total_transfer_cost=round(total_cost, 2),
        net_value=round(net_value, 2),
        transfers=transfers,
        source_relief=source_relief,
        diagnostics=diagnostics,
    )


# ─── Diagnostics ─────────────────────────────────────────────────────────────


def _build_diagnostics(
    transfers: list[dict],
    candidates: pd.DataFrame,
    elapsed_ms: float,
) -> dict:
    """Build diagnostic summary."""
    if not transfers:
        return {"solve_time_ms": round(elapsed_ms, 1)}

    df = pd.DataFrame(transfers)
    return {
        "solve_time_ms": round(elapsed_ms, 1),
        "reason_breakdown": df["reason"].value_counts().to_dict(),
        "lifecycle_breakdown": df["lifecycle_stage"].value_counts().to_dict(),
        "unique_source_stores": int(df["from_store_id"].nunique()),
        "unique_destination_stores": int(df["to_store_id"].nunique()),
        "unique_skus": int(df["sku_id"].nunique()),
        "avg_qty_per_transfer": round(float(df["qty"].mean()), 1),
        "avg_net_value_per_transfer": round(float(df["net_value"].mean()), 2),
        "total_candidates_evaluated": len(candidates),
        "selection_rate": round(len(transfers) / max(len(candidates), 1), 3),
    }
