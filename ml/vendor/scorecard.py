"""Vendor scorecard metrics.

Computes vendor performance scores used for sourcing decisions:
- on_time_delivery_rate: % of POs delivered on or before expected date
- lead_time_adherence: how closely actual lead times match stated lead times
- quality_pass_rate: % of received units passing quality checks
- capacity_accuracy: how well vendor meets committed capacity
- forecast_adherence: vendor's accuracy in meeting forecast-committed quantities

Each metric is 0–1.  The composite score is a weighted average.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ScorecardWeights:
    """Weights for the composite vendor score."""

    on_time_delivery: float = 0.30
    lead_time_adherence: float = 0.20
    quality_pass_rate: float = 0.20
    capacity_accuracy: float = 0.15
    forecast_adherence: float = 0.15


@dataclass
class VendorScorecard:
    """Full scorecard for a single vendor."""

    vendor_id: str
    vendor_name: str
    # Individual metrics (0–1)
    on_time_delivery_rate: float
    lead_time_adherence: float
    quality_pass_rate: float
    capacity_accuracy: float
    forecast_adherence: float
    # Composite
    composite_score: float
    # Supporting stats
    total_pos: int = 0
    received_pos: int = 0
    total_units_ordered: int = 0
    avg_delivery_delay_days: float = 0.0
    total_skus: int = 0
    active_skus: int = 0
    is_active: bool = True
    # Tier classification
    tier: str = "standard"  # preferred, standard, probation, inactive


def compute_on_time_delivery_rate(
    on_time_deliveries: int, total_received: int
) -> float:
    """On-time delivery rate = on_time_deliveries / total_received."""
    if total_received <= 0:
        return 1.0  # No data = benefit of doubt
    return round(min(1.0, on_time_deliveries / total_received), 4)


def compute_lead_time_adherence(
    avg_actual_delay_days: float, stated_lead_time_days: int
) -> float:
    """Lead time adherence: 1 - (avg_delay / stated_lead_time), clamped to [0, 1].

    A vendor with 0 delay scores 1.0.  One averaging 50% of stated LT as delay scores 0.5.
    """
    if stated_lead_time_days <= 0:
        return 1.0
    delay_ratio = max(0, avg_actual_delay_days) / stated_lead_time_days
    return round(max(0.0, min(1.0, 1.0 - delay_ratio)), 4)


def compute_quality_pass_rate(
    units_passed: int, units_received: int
) -> float:
    """Quality pass rate = units_passed / units_received."""
    if units_received <= 0:
        return 1.0
    return round(min(1.0, units_passed / units_received), 4)


def compute_capacity_accuracy(
    units_delivered: int, units_committed: int
) -> float:
    """Capacity accuracy = min(delivered / committed, 1.0).

    Measures whether vendor delivers what they committed to.
    """
    if units_committed <= 0:
        return 1.0
    return round(min(1.0, units_delivered / units_committed), 4)


def compute_forecast_adherence(
    units_delivered: int, units_forecast_shared: int
) -> float:
    """Forecast adherence = min(delivered / forecast_shared, 1.0).

    Measures vendor's ability to meet the forecasted demand shared with them.
    """
    if units_forecast_shared <= 0:
        return 1.0
    return round(min(1.0, units_delivered / units_forecast_shared), 4)


def compute_composite_score(
    on_time_delivery_rate: float,
    lead_time_adherence: float,
    quality_pass_rate: float,
    capacity_accuracy: float,
    forecast_adherence: float,
    weights: ScorecardWeights | None = None,
) -> float:
    """Weighted composite vendor score."""
    if weights is None:
        weights = ScorecardWeights()
    score = (
        on_time_delivery_rate * weights.on_time_delivery
        + lead_time_adherence * weights.lead_time_adherence
        + quality_pass_rate * weights.quality_pass_rate
        + capacity_accuracy * weights.capacity_accuracy
        + forecast_adherence * weights.forecast_adherence
    )
    return round(score, 4)


def classify_vendor_tier(composite_score: float, is_active: bool) -> str:
    """Classify vendor into tiers based on composite score."""
    if not is_active:
        return "inactive"
    if composite_score >= 0.90:
        return "preferred"
    if composite_score >= 0.70:
        return "standard"
    return "probation"


def build_vendor_scorecard(
    vendor_row: dict,
    weights: ScorecardWeights | None = None,
) -> VendorScorecard:
    """Build a full scorecard for a single vendor from mart_vendor_performance data.

    Args:
        vendor_row: dict with vendor performance columns from mart or synthetic data.
        weights: optional custom weights.
    """
    vendor_id = vendor_row.get("vendor_id", "")
    vendor_name = vendor_row.get("vendor_name", "")
    is_active = bool(vendor_row.get("is_active", True))

    total_received = int(vendor_row.get("received_pos", 0))
    on_time = int(vendor_row.get("on_time_deliveries", 0))
    avg_delay = float(vendor_row.get("avg_delivery_delay_days", 0))
    stated_lt = int(vendor_row.get("avg_lead_time_days", 7))
    total_ordered = int(vendor_row.get("total_units_ordered", 0))

    # Compute individual metrics
    otd = compute_on_time_delivery_rate(on_time, total_received)
    lta = compute_lead_time_adherence(avg_delay, stated_lt)

    # Quality: use reliability_score as proxy when actual QC data unavailable
    quality = float(vendor_row.get("quality_pass_rate", vendor_row.get("reliability_score", 0.9)))
    qpr = round(min(1.0, max(0.0, quality)), 4)

    # Capacity accuracy: use total_units_ordered as committed proxy
    units_delivered = int(vendor_row.get("units_delivered", total_ordered))
    units_committed = int(vendor_row.get("units_committed", total_ordered))
    ca = compute_capacity_accuracy(units_delivered, units_committed)

    # Forecast adherence: use total_units_ordered vs forecast_shared
    forecast_shared = int(vendor_row.get("forecast_shared_units", total_ordered))
    fa = compute_forecast_adherence(units_delivered, forecast_shared)

    composite = compute_composite_score(otd, lta, qpr, ca, fa, weights)
    tier = classify_vendor_tier(composite, is_active)

    return VendorScorecard(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        on_time_delivery_rate=otd,
        lead_time_adherence=lta,
        quality_pass_rate=qpr,
        capacity_accuracy=ca,
        forecast_adherence=fa,
        composite_score=composite,
        total_pos=int(vendor_row.get("total_pos", 0)),
        received_pos=total_received,
        total_units_ordered=total_ordered,
        avg_delivery_delay_days=round(avg_delay, 1),
        total_skus=int(vendor_row.get("total_skus", 0)),
        active_skus=int(vendor_row.get("active_skus", 0)),
        is_active=is_active,
        tier=tier,
    )


def build_all_scorecards(
    vendor_data: pd.DataFrame,
    weights: ScorecardWeights | None = None,
) -> list[VendorScorecard]:
    """Build scorecards for all vendors."""
    scorecards = []
    for _, row in vendor_data.iterrows():
        sc = build_vendor_scorecard(row.to_dict(), weights)
        scorecards.append(sc)
    logger.info(f"Built scorecards for {len(scorecards)} vendors")
    return scorecards
