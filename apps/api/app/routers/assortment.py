"""Assortment optimization API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Request / Response models ────────────────────────────────────────────────


class OptimizeRequest(BaseModel):
    store_id: str | None = Field(None, description="Single store (None = all stores)")
    scenario: str | None = Field(None, description="Force scenario (e.g. metro_premium)")
    db_path: str = Field("data/dev.duckdb", description="DuckDB path")


class SkuSelection(BaseModel):
    sku_id: str
    store_id: str
    category: str
    subcategory: str
    brand: str
    sku_type: str
    is_display_only: int
    lifecycle_stage: str
    mrp: float
    composite_score: float
    action: str


class StoreResult(BaseModel):
    store_id: str
    status: str
    objective_value: float
    solve_time_ms: float
    total_capacity: int
    used_capacity: int
    selected_count: int
    diagnostics: dict = {}


class OptimizeResponse(BaseModel):
    stores_optimized: int
    results: list[StoreResult]


class StoreAssortmentResponse(BaseModel):
    store_id: str
    status: str
    objective_value: float
    total_capacity: int
    used_capacity: int
    selected_skus: list[dict]
    excluded_skus: list[dict]
    diagnostics: dict


class ScenarioInfo(BaseModel):
    name: str
    description: str
    weights: dict
    constraints: dict


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/optimize", response_model=OptimizeResponse)
def optimize_assortment(request: OptimizeRequest) -> Any:
    """Run assortment optimization for one or all stores.

    Uses CP-SAT solver with scenario-driven constraints.
    """
    from services.assortment.config import SCENARIOS, AssortmentConfig
    from services.assortment.pipeline import run_assortment_pipeline

    if request.scenario and request.scenario not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{request.scenario}'. "
                   f"Available: {list(SCENARIOS.keys())}",
        )

    config = AssortmentConfig(db_path=request.db_path)
    results = run_assortment_pipeline(
        config,
        store_id=request.store_id,
        scenario_override=request.scenario,
        write_to_db=True,
    )

    store_results = [
        StoreResult(
            store_id=r.store_id,
            status=r.status,
            objective_value=r.objective_value,
            solve_time_ms=r.solve_time_ms,
            total_capacity=r.total_capacity,
            used_capacity=r.used_capacity,
            selected_count=len(r.selected_skus),
            diagnostics=r.diagnostics,
        )
        for r in results
    ]

    return OptimizeResponse(
        stores_optimized=len(results),
        results=store_results,
    )


@router.get("/store/{store_id}", response_model=StoreAssortmentResponse)
def get_store_assortment(
    store_id: str,
    scenario: str | None = Query(None, description="Force scenario"),
    db_path: str = Query("data/dev.duckdb"),
) -> Any:
    """Get optimized assortment for a single store."""
    from services.assortment.config import SCENARIOS, AssortmentConfig
    from services.assortment.pipeline import run_assortment_pipeline

    if scenario and scenario not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{scenario}'. Available: {list(SCENARIOS.keys())}",
        )

    config = AssortmentConfig(db_path=db_path)
    results = run_assortment_pipeline(
        config,
        store_id=store_id,
        scenario_override=scenario,
        write_to_db=False,
    )

    if not results:
        raise HTTPException(status_code=404, detail=f"No results for store {store_id}")

    r = results[0]
    return StoreAssortmentResponse(
        store_id=r.store_id,
        status=r.status,
        objective_value=r.objective_value,
        total_capacity=r.total_capacity,
        used_capacity=r.used_capacity,
        selected_skus=r.selected_skus,
        excluded_skus=r.excluded_skus,
        diagnostics=r.diagnostics,
    )


@router.get("/scenarios")
def list_scenarios() -> list[ScenarioInfo]:
    """List all available assortment scenarios."""
    from services.assortment.config import SCENARIOS

    return [
        ScenarioInfo(
            name=name,
            description=s.description,
            weights={
                "demand": s.w_demand,
                "trial": s.w_trial,
                "margin": s.w_margin,
                "freshness": s.w_freshness,
                "new_launch": s.w_new_launch,
                "category_balance": s.w_category_balance,
            },
            constraints={
                "min_eyeglasses_pct": s.min_eyeglasses_pct,
                "min_sunglasses_pct": s.min_sunglasses_pct,
                "min_contact_lenses_pct": s.min_contact_lenses_pct,
                "max_depth_per_subcategory": s.max_depth_per_subcategory,
                "max_per_brand": s.max_per_brand,
                "min_new_launch_pct": s.min_new_launch_pct,
                "display_dummy_target_pct": s.display_dummy_target_pct,
            },
        )
        for name, s in SCENARIOS.items()
    ]


@router.get("/simulation")
def run_simulation(
    n_skus: int = Query(200, ge=10, le=1000),
    capacity: int = Query(80, ge=10, le=500),
    scenario: str = Query("metro_mass"),
) -> dict:
    """Run heuristic vs optimized comparison on synthetic data."""
    from services.assortment.config import SCENARIOS, AssortmentConfig
    from services.assortment.scoring import compute_sku_scores
    from services.assortment.simulation import (
        generate_synthetic_skus,
        run_comparison,
    )

    if scenario not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{scenario}'. Available: {list(SCENARIOS.keys())}",
        )

    config = AssortmentConfig()
    sc = SCENARIOS[scenario]
    skus = generate_synthetic_skus(n_skus)
    scored = compute_sku_scores(skus, sc, config)
    results = run_comparison(scored, capacity, sc, config)

    def _metrics_to_dict(m):
        return {
            "strategy": m.strategy,
            "total_score": m.total_score,
            "skus_selected": m.skus_selected,
            "capacity_utilization": m.capacity_utilization,
            "new_launch_pct": m.new_launch_pct,
            "brand_count": m.brand_count,
            "subcategory_count": m.subcategory_count,
            "display_dummy_pct": m.display_dummy_pct,
            "avg_demand_score": m.avg_demand_score,
            "avg_margin_score": m.avg_margin_score,
            "avg_freshness_score": m.avg_freshness_score,
            "width": m.width,
            "depth": m.depth,
            "category_mix": m.category_mix,
        }

    h = results["heuristic"]
    o = results["optimized"]
    improvement = (
        (o.total_score - h.total_score) / h.total_score * 100
        if h.total_score > 0 else 0
    )

    return {
        "scenario": scenario,
        "n_skus": n_skus,
        "capacity": capacity,
        "heuristic": _metrics_to_dict(h),
        "optimized": _metrics_to_dict(o),
        "score_improvement_pct": round(improvement, 1),
    }
