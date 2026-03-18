# Product Lifecycle Intelligence v1

## Overview

Product Lifecycle Intelligence classifies each SKU into one of six lifecycle stages and generates lifecycle-aware recommended actions. This enables downstream services (forecasting, assortment, replenishment, transfers) to make stage-appropriate decisions.

## Lifecycle Stages

| Stage | Description | Default Action | Freshness Score |
|-------|-------------|---------------|-----------------|
| **Launch** | Recently introduced, < 60 days old | Expand distribution | 1.0 |
| **Growth** | Positive sales velocity and trial trends | Expand distribution | 0.85 |
| **Core** | Stable high performer (≥70% of peak) | Protect placement | 0.7 |
| **Maturity** | Stable but flattening performance | Protect placement | 0.5 |
| **Decline** | Falling sales velocity and engagement | Reduce depth | 0.25 |
| **Exit** | Very low performance, high aging inventory | Discontinue | 0.0 |

## Recommended Actions

| Action | When Applied |
|--------|-------------|
| **Expand distribution** | Launch & growth SKUs — increase store coverage |
| **Protect placement** | Core & maturity SKUs — maintain display presence |
| **Reduce depth** | Maturity with aging inventory, early decline |
| **Transfer** | Decline SKUs with moderate aging — move to stores with demand |
| **Markdown** | Decline SKUs with high aging inventory (≥60%) |
| **Discontinue** | Exit stage — remove from assortment |

## Architecture

```
services/lifecycle/
├── __init__.py
├── config.py        # Thresholds, weights, business rules
├── features.py      # Feature engineering from raw data
├── classifier.py    # Rule-based v1 classification
├── scoring.py       # Survival-analysis v2 scoring
└── pipeline.py      # Orchestration & DB I/O

schemas/lifecycle.py  # Pydantic models (LifecycleStage, LifecycleFeatures, etc.)
apps/api/app/routers/lifecycle.py  # REST API endpoints
```

## Feature Set

| Feature | Source | Description |
|---------|--------|-------------|
| `age_days` | SKU master / first sale | Days since launch |
| `sales_velocity_trend` | Weekly sales | Normalized slope of recent sales |
| `trial_trend` | Trial events | Normalized slope of trial activity |
| `conversion_trend` | Trials + sales | Slope of trial-to-sale conversion |
| `aging_inventory_pct` | Inventory snapshots | Fraction of inventory past 90 days |
| `markdown_count` | Promotions | Historical markdown events |
| `avg_weekly_sales` | Weekly sales | Mean weekly units sold |
| `weeks_of_history` | Weekly sales | Total weeks of data |
| `peak_weekly_sales` | Weekly sales | Historical maximum weekly sales |
| `current_vs_peak_ratio` | Weekly sales | Current avg / peak (0-1) |

## Classification Engine

### V1: Rule-Based Classifier

Rules are applied in priority order:

1. **EXIT** — age ≥ 180d, current/peak ≤ 20%, aging ≥ 50%
2. **LAUNCH** — age ≤ 60d, history ≤ 8 weeks
3. **GROWTH** — velocity trend ≥ +0.05, trial trend ≥ 0, age ≤ 365d
4. **DECLINE** — velocity trend ≤ -0.05, current/peak ≤ 50%, age ≥ 120d
5. **CORE** — current/peak ≥ 70%, avg sales ≥ 1.0/wk, aging ≤ 30%
6. **MATURITY** — fallback for established SKUs

Confidence is calibrated based on:
- Base confidence: 0.70
- Agreement bonus: +0.15 when multiple signals align
- Low-data penalty: -0.20 when history < 12 weeks

### V2: Survival-Analysis Scoring (Optional)

Provides a continuous `survival_score` (0-1) using Weibull-inspired modelling:

- **Base survival**: `S(t) = exp(-(t/scale)^shape)` with shape=1.5, scale=365
- **Signal modifiers**: velocity, trial, conversion, aging, markdown factors
- **Composite score**: Weighted combination of all factors
- **Hazard rate**: Instantaneous risk of lifecycle decline
- **Expected remaining weeks**: Estimated productive life

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/lifecycle/classify` | Run classification for one/all SKUs |
| GET | `/api/v1/lifecycle/sku/{sku_id}` | Get classification for single SKU |
| GET | `/api/v1/lifecycle/sku/{sku_id}/survival-score` | Get v2 survival score |
| GET | `/api/v1/lifecycle/summary` | Aggregate lifecycle summary |
| GET | `/api/v1/lifecycle/stages` | List all stages with metadata |

## Integration Points

### Forecasting (`ml/forecasting/`)

Lifecycle stage adjusts forecast behavior via `LIFECYCLE_FORECAST_ADJUSTMENTS`:

- **Launch**: Forecast floor of 1.0 unit, 1.5x uncertainty multiplier (don't underforecast new products)
- **Growth**: Forecast floor of 0.5 unit, 1.2x uncertainty
- **Core/Maturity**: Standard forecasting (1.0x uncertainty)
- **Decline**: 1.3x uncertainty (demand is volatile)
- **Exit**: 1.5x uncertainty

Applied in `ml/forecasting/predict.py::_apply_lifecycle_adjustments()`.

### Assortment (`services/assortment/`)

Lifecycle freshness scores feed directly into the assortment scoring engine:

- `LIFECYCLE_FRESHNESS_SCORES` merged with `AssortmentConfig.freshness_scores`
- Stale penalty extended to include `decline` (0.4) and `exit` (1.0) stages
- New launch detection uses lifecycle stage for the `new_launch_score` component

Applied in `services/assortment/scoring.py::compute_sku_scores()`.

### Replenishment (`services/replenishment/`)

Lifecycle stage informs replenishment decisions via the classification output table (`main_ml.lifecycle_classifications`):

- Exit SKUs: Should not be replenished
- Decline SKUs: Reduce reorder quantities
- Launch SKUs: Ensure initial stock levels

### Transfers (`services/transfers/`)

The `recommended_action` field directly maps to transfer eligibility:

- `transfer` action → prioritize inter-store rebalancing
- `discontinue` action → exclude from transfers, route to markdown

## Data Flow

```
Raw Data (sales, trials, inventory, SKU master)
    │
    ▼
Feature Engineering (services/lifecycle/features.py)
    │
    ▼
┌──────────────────────────┐
│ V1: Rule-Based Classifier │──► LifecycleClassification
│ (services/lifecycle/      │     - lifecycle_stage
│  classifier.py)           │     - confidence
│                           │     - recommended_action
└──────────────────────────┘
    │
    ▼ (optional)
┌──────────────────────────┐
│ V2: Survival Scoring      │──► survival_score, hazard_rate,
│ (services/lifecycle/      │    expected_remaining_weeks
│  scoring.py)              │
└──────────────────────────┘
    │
    ▼
DuckDB: main_ml.lifecycle_classifications
    │
    ├──► Forecasting (forecast adjustments)
    ├──► Assortment (freshness scoring)
    ├──► Replenishment (reorder decisions)
    └──► Transfers (rebalancing priority)
```

## Usage

### CLI

```bash
# Classify all SKUs
python -m services.lifecycle.pipeline

# Classify single SKU
python -m services.lifecycle.pipeline --sku SKU_001

# Include v2 survival scoring
python -m services.lifecycle.pipeline --v2-scoring

# Output to CSV
python -m services.lifecycle.pipeline --output lifecycle_results.csv
```

### API

```bash
# Classify all SKUs
curl -X POST http://localhost:8000/api/v1/lifecycle/classify \
  -H "Content-Type: application/json" \
  -d '{"include_v2_scoring": true}'

# Get single SKU classification
curl http://localhost:8000/api/v1/lifecycle/sku/SKU_001

# Get survival score
curl http://localhost:8000/api/v1/lifecycle/sku/SKU_001/survival-score

# Get aggregate summary
curl http://localhost:8000/api/v1/lifecycle/summary
```

## Configuration

All thresholds are configurable via `LifecycleConfig` dataclass in `services/lifecycle/config.py`. Key parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trend_window_weeks` | 8 | Weeks used for trend slope calculation |
| `launch_max_age_days` | 60 | Maximum age to be classified as launch |
| `growth_min_velocity_trend` | 0.05 | Minimum positive trend for growth |
| `core_min_current_vs_peak` | 0.70 | Minimum current/peak ratio for core |
| `exit_min_aging_pct` | 0.50 | Minimum aging % for exit classification |
| `survival_shape` | 1.5 | Weibull shape parameter |
| `survival_scale` | 365 | Weibull scale parameter (days) |

## Testing

```bash
# Run lifecycle tests
pytest tests/unit/test_lifecycle.py -v

# Run all tests
make test
```
