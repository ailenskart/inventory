"""Feast feature store integration for demand forecasting.

Defines feature views and entity definitions for serving features
at training and inference time.

Feature groups:
- demand_features: Lagged sales, rolling averages, demand signals
- inventory_features: Stock levels, stockout history
- store_features: Cluster, format, traffic patterns
- product_features: Category, lifecycle, price tier
- calendar_features: Seasonality, festive flags

Usage:
    feast apply  (from feature_repo directory)
    feast materialize  (backfill offline store)
"""

import logging
import os
from datetime import timedelta

logger = logging.getLogger(__name__)


def get_feature_store_config() -> dict:
    """Return Feast feature store configuration."""
    return {
        "project": "lenskart_demand",
        "registry": "data/feast/registry.db",
        "provider": "local",
        "online_store": {
            "type": "sqlite",
            "path": "data/feast/online_store.db",
        },
        "offline_store": {
            "type": "duckdb",
            "path": "data/dev.duckdb",
        },
    }


def write_feature_repo(repo_dir: str = "ml/forecasting/feature_repo"):
    """Generate Feast feature repository files.

    Creates feature_store.yaml and feature definitions.
    """
    os.makedirs(repo_dir, exist_ok=True)

    # feature_store.yaml
    config = """project: lenskart_demand
registry: ../../../data/feast/registry.db
provider: local
online_store:
  type: sqlite
  path: ../../../data/feast/online_store.db
entity_key_serialization_version: 2
"""
    with open(os.path.join(repo_dir, "feature_store.yaml"), "w") as f:
        f.write(config)

    # Feature definitions
    features_py = '''"""Feast feature definitions for demand forecasting."""

from datetime import timedelta

from feast import Entity, Feature, FeatureView, Field, FileSource
from feast.types import Float32, Int64, String


# ─── Entities ───────────────────────────────────────────────────────────────

store_entity = Entity(
    name="store_id",
    description="Retail store identifier",
)

sku_entity = Entity(
    name="sku_id",
    description="SKU / product identifier",
)

store_sku_entity = Entity(
    name="store_sku_id",
    description="Store-SKU combination",
)


# ─── Sources ────────────────────────────────────────────────────────────────

demand_source = FileSource(
    path="../../../data/features/demand_features.parquet",
    timestamp_field="week_start",
)

inventory_source = FileSource(
    path="../../../data/features/inventory_features.parquet",
    timestamp_field="snapshot_date",
)


# ─── Feature Views ──────────────────────────────────────────────────────────

demand_features = FeatureView(
    name="demand_features",
    entities=[store_entity, sku_entity],
    ttl=timedelta(days=90),
    schema=[
        Field(name="total_qty_sold", dtype=Int64),
        Field(name="sell_through_signal", dtype=Int64),
        Field(name="prescription_order_signal", dtype=Int64),
        Field(name="display_interest_signal", dtype=Int64),
        Field(name="total_revenue", dtype=Float32),
        Field(name="lag_1w", dtype=Float32),
        Field(name="lag_4w", dtype=Float32),
        Field(name="lag_12w", dtype=Float32),
        Field(name="rolling_mean_4w", dtype=Float32),
        Field(name="rolling_mean_12w", dtype=Float32),
        Field(name="rolling_std_4w", dtype=Float32),
    ],
    source=demand_source,
    online=True,
)

inventory_features = FeatureView(
    name="inventory_features",
    entities=[store_entity, sku_entity],
    ttl=timedelta(days=30),
    schema=[
        Field(name="on_hand_qty", dtype=Int64),
        Field(name="available_qty", dtype=Int64),
        Field(name="weeks_of_supply", dtype=Float32),
        Field(name="is_stockout", dtype=Int64),
        Field(name="inventory_status", dtype=String),
    ],
    source=inventory_source,
    online=True,
)
'''
    with open(os.path.join(repo_dir, "features.py"), "w") as f:
        f.write(features_py)

    # Create __init__.py
    with open(os.path.join(repo_dir, "__init__.py"), "w") as f:
        f.write("")

    logger.info(f"Feature repo written to {repo_dir}")


def materialize_features(
    demand_df=None,
    inventory_df=None,
    output_dir: str = "data/features",
):
    """Materialize features to parquet for Feast offline store.

    Converts DataFrames to parquet files that Feast can read.
    """
    os.makedirs(output_dir, exist_ok=True)

    if demand_df is not None:
        demand_path = os.path.join(output_dir, "demand_features.parquet")
        demand_df.to_parquet(demand_path, index=False)
        logger.info(f"Demand features materialized: {len(demand_df)} rows → {demand_path}")

    if inventory_df is not None:
        inv_path = os.path.join(output_dir, "inventory_features.parquet")
        inventory_df.to_parquet(inv_path, index=False)
        logger.info(f"Inventory features materialized: {len(inventory_df)} rows → {inv_path}")
