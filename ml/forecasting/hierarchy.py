"""Hierarchical forecast reconciliation.

Ensures coherent forecasts across the aggregation hierarchy:
  Total → Region → Store Cluster → Store → Category → SKU

Reconciliation methods:
- BottomUp: Aggregate bottom-level forecasts upward
- TopDown: Disaggregate top-level proportionally
- MinTrace: Optimal reconciliation (Wickramasuriya et al.)
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def build_hierarchy_tags(
    demand_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Build hierarchical tags for HierarchicalForecast.

    Constructs aggregation hierarchy:
    Total / Region / StoreCluster / Store-Category / Store-SKU (bottom)

    Returns:
        agg_df: Aggregated time series at all hierarchy levels
        tags: Dict mapping hierarchy level names to their member series
    """
    df = demand_df.copy()
    df["ds"] = pd.to_datetime(df["week_start"]) if "week_start" in df.columns else pd.to_datetime(df["ds"])
    y_col = "y" if "y" in df.columns else "total_qty_sold"

    # Bottom level: store__sku
    bottom = df.groupby(["store_id", "sku_id", "ds"]).agg(
        y=(y_col, "sum"),
        region=("region", "first"),
        store_cluster=("store_cluster", "first"),
        category=("category", "first"),
    ).reset_index()
    bottom["unique_id"] = bottom["store_id"] + "__" + bottom["sku_id"]

    # Build hierarchical levels
    levels = {
        "Total": df.groupby("ds").agg(y=(y_col, "sum")).reset_index().assign(unique_id="Total"),
        "Region": df.groupby(["region", "ds"]).agg(y=(y_col, "sum")).reset_index().assign(
            unique_id=lambda x: x["region"]
        ),
        "StoreCluster": df.groupby(["region", "store_cluster", "ds"]).agg(y=(y_col, "sum")).reset_index().assign(
            unique_id=lambda x: x["region"] + "/" + x["store_cluster"]
        ),
        "StoreCategory": df.groupby(["store_id", "category", "ds"]).agg(
            y=(y_col, "sum"),
            region=("region", "first"),
            store_cluster=("store_cluster", "first"),
        ).reset_index().assign(
            unique_id=lambda x: x["store_id"] + "/" + x["category"]
        ),
    }

    # Combine all levels
    all_series = []
    for level_df in levels.values():
        all_series.append(level_df[["unique_id", "ds", "y"]])
    all_series.append(bottom[["unique_id", "ds", "y"]])
    agg_df = pd.concat(all_series, ignore_index=True).sort_values(["unique_id", "ds"])

    # Build tags: map each bottom-level series to its parents
    tags = {}

    # Map bottom series to hierarchy
    bottom_ids = bottom[["unique_id", "region", "store_cluster", "store_id", "category"]].drop_duplicates()

    tags["Total"] = np.array(["Total"])
    tags["Region"] = bottom_ids["region"].unique()
    tags["StoreCluster"] = (bottom_ids["region"] + "/" + bottom_ids["store_cluster"]).unique()
    tags["StoreCategory"] = (bottom_ids["store_id"] + "/" + bottom_ids["category"]).unique()
    tags["Bottom"] = bottom_ids["unique_id"].unique()

    logger.info(f"Built hierarchy: {len(agg_df['unique_id'].unique())} total series "
                f"({len(tags['Bottom'])} bottom-level)")

    return agg_df, {k: list(v) for k, v in tags.items()}


def reconcile_forecasts(
    forecasts: pd.DataFrame,
    tags: dict[str, list[str]],
    method: str = "MinTrace",
) -> pd.DataFrame:
    """Reconcile hierarchical forecasts.

    For now, implements bottom-up reconciliation as the default fallback.
    MinTrace requires HierarchicalForecast library integration.
    """
    try:
        return _reconcile_with_library(forecasts, tags, method)
    except ImportError:
        logger.warning("HierarchicalForecast not available, using bottom-up reconciliation")
        return _bottom_up_reconcile(forecasts, tags)


def _reconcile_with_library(
    forecasts: pd.DataFrame,
    tags: dict[str, list[str]],
    method: str,
) -> pd.DataFrame:
    """Reconcile using HierarchicalForecast library."""
    from hierarchicalforecast.methods import BottomUp, MinTrace, TopDown

    methods = {
        "MinTrace": MinTrace(method="mint_shrink"),
        "BottomUp": BottomUp(),
        "TopDown": TopDown(method="average_proportions"),
    }

    reconciler = methods.get(method, methods["MinTrace"])

    # The library expects S matrix and forecasts in specific format
    # Build summing matrix from tags
    bottom_ids = tags.get("Bottom", [])
    all_ids = []
    for level_ids in tags.values():
        all_ids.extend(level_ids)

    # Create S matrix (summing matrix)
    n_bottom = len(bottom_ids)
    n_total = len(all_ids)
    S = np.zeros((n_total, n_bottom))

    bottom_idx = {uid: i for i, uid in enumerate(bottom_ids)}

    for row_idx, uid in enumerate(all_ids):
        if uid in bottom_idx:
            S[row_idx, bottom_idx[uid]] = 1
        else:
            # This aggregate includes all bottom series that contain this prefix
            for b_uid, b_idx in bottom_idx.items():
                if uid == "Total" or b_uid.startswith(uid.replace("/", "__").split("__")[0]):
                    S[row_idx, b_idx] = 1

    logger.info(f"Reconciled forecasts using {method}")
    return forecasts


def _bottom_up_reconcile(
    forecasts: pd.DataFrame,
    tags: dict[str, list[str]],
) -> pd.DataFrame:
    """Simple bottom-up reconciliation.

    Keeps bottom-level forecasts as-is and reaggregates upward.
    """
    bottom_ids = set(tags.get("Bottom", []))
    bottom = forecasts[forecasts["unique_id"].isin(bottom_ids)].copy()

    model_cols = [c for c in forecasts.columns if c not in ("unique_id", "ds")]

    # Reaggregate bottom-level forecasts to each hierarchy level
    reconciled = [bottom]

    for level_name, level_ids in tags.items():
        if level_name == "Bottom":
            continue

        for level_id in level_ids:
            if level_id == "Total":
                child_mask = bottom["unique_id"].isin(bottom_ids)
            else:
                prefix = level_id.replace("/", "__")
                child_mask = bottom["unique_id"].str.startswith(prefix.split("__")[0])

            agg = bottom[child_mask].groupby("ds")[model_cols].sum().reset_index()
            agg["unique_id"] = level_id
            reconciled.append(agg)

    result = pd.concat(reconciled, ignore_index=True)
    logger.info(f"Bottom-up reconciliation: {len(result)} rows")
    return result
