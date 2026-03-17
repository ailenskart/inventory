"""Product Lifecycle Intelligence API endpoints."""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Request / Response models ────────────────────────────────────────────────


class ClassifyRequest(BaseModel):
    sku_id: str | None = Field(None, description="Single SKU (None = all SKUs)")
    include_v2_scoring: bool = Field(False, description="Include survival-analysis scoring")
    db_path: str = Field("data/dev.duckdb", description="DuckDB path")


class SkuClassification(BaseModel):
    sku_id: str
    lifecycle_stage: str
    confidence: float
    recommended_action: str
    reason: str
    age_days: int
    sales_velocity_trend: float
    current_vs_peak_ratio: float


class ClassifyResponse(BaseModel):
    total_skus: int
    stage_counts: dict[str, int]
    action_counts: dict[str, int]
    avg_confidence: float
    classifications: list[SkuClassification]


class SurvivalScoreResponse(BaseModel):
    sku_id: str
    survival_score: float
    hazard_rate: float
    expected_remaining_weeks: float
    age_days: int
    sales_velocity_trend: float


class LifecycleStageInfo(BaseModel):
    stage: str
    description: str
    default_action: str
    freshness_score: float


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/classify", response_model=ClassifyResponse)
def classify_skus(request: ClassifyRequest) -> Any:
    """Run lifecycle classification for one or all SKUs.

    Uses rule-based v1 classifier with optional survival-analysis v2 scoring.
    """
    from services.lifecycle.config import LifecycleConfig
    from services.lifecycle.pipeline import build_summary, run_lifecycle_pipeline

    config = LifecycleConfig(db_path=request.db_path)
    classifications, _ = run_lifecycle_pipeline(
        config,
        sku_id=request.sku_id,
        include_v2_scoring=request.include_v2_scoring,
        write_to_db=True,
    )

    if not classifications:
        raise HTTPException(
            status_code=404,
            detail="No SKUs found or insufficient data for classification",
        )

    summary = build_summary(classifications)
    items = [
        SkuClassification(
            sku_id=c.sku_id,
            lifecycle_stage=c.lifecycle_stage.value,
            confidence=c.confidence,
            recommended_action=c.recommended_action.value,
            reason=c.reason,
            age_days=c.features.age_days,
            sales_velocity_trend=c.features.sales_velocity_trend,
            current_vs_peak_ratio=c.features.current_vs_peak_ratio,
        )
        for c in classifications
    ]

    return ClassifyResponse(
        total_skus=summary.total_skus,
        stage_counts=summary.stage_counts,
        action_counts=summary.action_counts,
        avg_confidence=summary.avg_confidence,
        classifications=items,
    )


@router.get("/sku/{sku_id}")
def get_sku_lifecycle(
    sku_id: str,
    db_path: str = Query("data/dev.duckdb"),
) -> SkuClassification:
    """Get lifecycle classification for a single SKU."""
    from services.lifecycle.config import LifecycleConfig
    from services.lifecycle.pipeline import run_lifecycle_pipeline

    config = LifecycleConfig(db_path=db_path)
    classifications, _ = run_lifecycle_pipeline(
        config,
        sku_id=sku_id,
        write_to_db=False,
    )

    if not classifications:
        raise HTTPException(status_code=404, detail=f"No lifecycle data for SKU {sku_id}")

    c = classifications[0]
    return SkuClassification(
        sku_id=c.sku_id,
        lifecycle_stage=c.lifecycle_stage.value,
        confidence=c.confidence,
        recommended_action=c.recommended_action.value,
        reason=c.reason,
        age_days=c.features.age_days,
        sales_velocity_trend=c.features.sales_velocity_trend,
        current_vs_peak_ratio=c.features.current_vs_peak_ratio,
    )


@router.get("/sku/{sku_id}/survival-score")
def get_sku_survival_score(
    sku_id: str,
    db_path: str = Query("data/dev.duckdb"),
) -> SurvivalScoreResponse:
    """Get survival-analysis score (v2) for a single SKU."""
    from services.lifecycle.config import LifecycleConfig
    from services.lifecycle.pipeline import run_lifecycle_pipeline

    config = LifecycleConfig(db_path=db_path)
    _, v2_scores = run_lifecycle_pipeline(
        config,
        sku_id=sku_id,
        include_v2_scoring=True,
        write_to_db=False,
    )

    if v2_scores is None or v2_scores.empty:
        raise HTTPException(status_code=404, detail=f"No survival score for SKU {sku_id}")

    row = v2_scores.iloc[0]
    return SurvivalScoreResponse(
        sku_id=row["sku_id"],
        survival_score=float(row["survival_score"]),
        hazard_rate=float(row["hazard_rate"]),
        expected_remaining_weeks=float(row["expected_remaining_weeks"]),
        age_days=int(row["age_days"]),
        sales_velocity_trend=float(row["sales_velocity_trend"]),
    )


@router.get("/summary")
def get_lifecycle_summary(
    db_path: str = Query("data/dev.duckdb"),
) -> dict:
    """Get aggregate lifecycle summary across all SKUs."""
    from services.lifecycle.config import LifecycleConfig
    from services.lifecycle.pipeline import build_summary, run_lifecycle_pipeline

    config = LifecycleConfig(db_path=db_path)
    classifications, _ = run_lifecycle_pipeline(
        config,
        write_to_db=False,
    )

    if not classifications:
        return {
            "total_skus": 0,
            "stage_counts": {},
            "action_counts": {},
            "avg_confidence": 0.0,
        }

    summary = build_summary(classifications)
    return {
        "total_skus": summary.total_skus,
        "stage_counts": summary.stage_counts,
        "action_counts": summary.action_counts,
        "avg_confidence": summary.avg_confidence,
    }


@router.get("/stages")
def list_lifecycle_stages() -> list[LifecycleStageInfo]:
    """List all lifecycle stages with descriptions and default actions."""
    from services.lifecycle.config import (
        LIFECYCLE_FRESHNESS_SCORES,
        STAGE_DEFAULT_ACTIONS,
    )

    descriptions = {
        "launch": "Recently introduced SKU with limited sales history",
        "growth": "SKU with increasing sales velocity and trial activity",
        "core": "Stable high-performing SKU that anchors the assortment",
        "maturity": "Established SKU with stable but flattening performance",
        "decline": "SKU with decreasing sales and engagement metrics",
        "exit": "End-of-life SKU recommended for discontinuation",
    }

    return [
        LifecycleStageInfo(
            stage=stage,
            description=descriptions[stage],
            default_action=STAGE_DEFAULT_ACTIONS[stage],
            freshness_score=LIFECYCLE_FRESHNESS_SCORES[stage],
        )
        for stage in STAGE_DEFAULT_ACTIONS
    ]
