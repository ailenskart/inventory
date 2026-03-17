"""Product Lifecycle Intelligence schemas."""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class LifecycleStage(str, Enum):
    """Product lifecycle stages from launch to exit."""

    LAUNCH = "launch"
    GROWTH = "growth"
    CORE = "core"
    MATURITY = "maturity"
    DECLINE = "decline"
    EXIT = "exit"


class RecommendedAction(str, Enum):
    """Lifecycle-aware recommended actions."""

    EXPAND_DISTRIBUTION = "expand_distribution"
    PROTECT_PLACEMENT = "protect_placement"
    REDUCE_DEPTH = "reduce_depth"
    TRANSFER = "transfer"
    MARKDOWN = "markdown"
    DISCONTINUE = "discontinue"


class LifecycleFeatures(BaseModel):
    """Feature set computed for lifecycle classification."""

    sku_id: str
    age_days: int = Field(ge=0, description="Days since launch")
    sales_velocity_trend: float = Field(
        description="Slope of recent sales velocity (positive = growing)"
    )
    trial_trend: float = Field(
        description="Slope of recent trial activity (positive = growing)"
    )
    conversion_trend: float = Field(
        description="Slope of trial-to-sale conversion rate"
    )
    aging_inventory_pct: float = Field(
        ge=0.0, le=1.0,
        description="Fraction of inventory considered aging (>90 days on hand)",
    )
    markdown_count: int = Field(
        ge=0, description="Number of historical markdowns"
    )
    avg_weekly_sales: float = Field(ge=0.0, description="Average weekly units sold")
    weeks_of_history: int = Field(ge=0, description="Weeks of sales data available")
    peak_weekly_sales: float = Field(ge=0.0, description="Historical peak weekly sales")
    current_vs_peak_ratio: float = Field(
        ge=0.0, le=1.0,
        description="Current sales as fraction of peak sales",
    )


class LifecycleClassification(BaseModel):
    """Output of lifecycle classification for a single SKU."""

    sku_id: str
    lifecycle_stage: LifecycleStage
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence")
    recommended_action: RecommendedAction
    reason: str = Field(description="Human-readable explanation")
    features: LifecycleFeatures
    classifier_version: str = "v1_rules"
    classified_at: datetime = Field(default_factory=datetime.now)


class LifecycleSummary(BaseModel):
    """Aggregate lifecycle summary across SKUs."""

    total_skus: int
    stage_counts: dict[str, int]
    action_counts: dict[str, int]
    avg_confidence: float
    classified_at: datetime = Field(default_factory=datetime.now)
