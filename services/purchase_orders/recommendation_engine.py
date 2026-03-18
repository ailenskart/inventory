"""PO recommendation engine.

Translates demand forecasts and inventory gaps into vendor-facing
purchase order recommendations:
1. Aggregate demand by vendor using replenishment recommendations
2. Score and rank vendors using scorecards
3. Allocate quantities across vendors (preferred + alternates)
4. Apply MOQ/MOV and capacity constraints
5. Generate PO recommendations with timing
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from ml.vendor.scorecard import VendorScorecard, build_vendor_scorecard
from services.purchase_orders.config import PurchaseOrderConfig

logger = logging.getLogger(__name__)


@dataclass
class PORecommendation:
    """A single PO recommendation."""

    po_id: str
    vendor_id: str
    vendor_name: str
    vendor_tier: str
    order_date: str
    expected_delivery_date: str
    lead_time_days: int
    lines: list[dict] = field(default_factory=list)
    total_qty: int = 0
    total_value: float = 0.0
    num_lines: int = 0
    status: str = "recommended"
    moq_met: bool = True
    mov_met: bool = True
    has_new_skus: bool = False
    urgency: str = "normal"
    split_from: str | None = None  # parent PO if this was split


@dataclass
class PORecommendationResult:
    """Result of PO recommendation generation."""

    recommendations: list[PORecommendation] = field(default_factory=list)
    total_pos: int = 0
    total_units: int = 0
    total_value: float = 0.0
    vendors_used: int = 0
    skus_covered: int = 0
    split_orders: int = 0
    diagnostics: dict = field(default_factory=dict)


def select_vendor(
    sku_id: str,
    vendor_scorecards: dict[str, VendorScorecard],
    sku_vendor_map: dict[str, list[str]],
    config: PurchaseOrderConfig,
    is_new_sku: bool = False,
) -> list[tuple[str, float]]:
    """Select vendor(s) for a SKU with allocation percentages.

    Returns list of (vendor_id, allocation_pct) tuples.
    For single-vendor: [(vendor_id, 1.0)]
    For split: [(preferred, 0.7), (alternate, 0.3)]
    """
    candidate_vendors = sku_vendor_map.get(sku_id, [])
    if not candidate_vendors:
        return []

    # Filter by min score and active status
    eligible = []
    for vid in candidate_vendors:
        sc = vendor_scorecards.get(vid)
        if sc and sc.is_active and sc.composite_score >= config.min_vendor_score:
            eligible.append((vid, sc))

    if not eligible:
        # Fallback: use any active vendor regardless of score
        for vid in candidate_vendors:
            sc = vendor_scorecards.get(vid)
            if sc and sc.is_active:
                eligible.append((vid, sc))

    if not eligible:
        return []

    # Sort by composite score (preferred vendor = highest score)
    eligible.sort(key=lambda x: x[1].composite_score, reverse=True)

    # New SKUs: preferred vendor only
    if is_new_sku and config.new_sku_preferred_vendor_only:
        return [(eligible[0][0], 1.0)]

    # Single vendor if only one eligible
    if len(eligible) == 1:
        return [(eligible[0][0], 1.0)]

    # Single vendor allocation
    return [(eligible[0][0], 1.0)]


def split_allocation(
    vendor_scores: list[tuple[str, VendorScorecard]],
    total_qty: int,
    config: PurchaseOrderConfig,
) -> list[tuple[str, float]]:
    """Split allocation across multiple vendors when order is large.

    Preferred vendor gets preferred_vendor_allocation_pct,
    remainder split proportionally by score among alternates.
    """
    if len(vendor_scores) <= 1:
        return [(vendor_scores[0][0], 1.0)] if vendor_scores else []

    preferred = vendor_scores[0]
    alternates = vendor_scores[1:]

    pref_pct = config.preferred_vendor_allocation_pct
    remaining_pct = 1.0 - pref_pct

    # Split remaining proportionally by score
    alt_total_score = sum(sc.composite_score for _, sc in alternates)
    allocations = [(preferred[0], pref_pct)]

    if alt_total_score > 0:
        for vid, sc in alternates:
            share = remaining_pct * (sc.composite_score / alt_total_score)
            allocations.append((vid, round(share, 4)))
    else:
        # Equal split among alternates
        for vid, _ in alternates:
            allocations.append((vid, round(remaining_pct / len(alternates), 4)))

    return allocations


def generate_po_recommendations(
    replenishment_recs: pd.DataFrame,
    vendor_data: pd.DataFrame,
    config: PurchaseOrderConfig,
    order_date: date | None = None,
) -> PORecommendationResult:
    """Generate PO recommendations from replenishment needs.

    Pipeline:
    1. Build vendor scorecards
    2. Group replenishment needs by vendor
    3. Select vendors and allocate quantities
    4. Apply MOQ/MOV constraints
    5. Generate PO recommendations with delivery dates

    Args:
        replenishment_recs: DataFrame from replenishment engine with
            sku_id, vendor_id, recommended_qty, urgency, destination_store, etc.
        vendor_data: DataFrame with vendor performance metrics.
        config: PO engine configuration.
        order_date: Date for PO generation (defaults to today).
    """
    if order_date is None:
        order_date = date.today()

    if replenishment_recs.empty:
        return PORecommendationResult()

    # Step 1: Build vendor scorecards
    scorecards: dict[str, VendorScorecard] = {}
    for _, row in vendor_data.iterrows():
        sc = build_vendor_scorecard(row.to_dict())
        scorecards[sc.vendor_id] = sc

    # Step 2: Build SKU → vendor map
    sku_vendor_map: dict[str, list[str]] = defaultdict(list)
    if "vendor_id" in replenishment_recs.columns:
        for _, row in replenishment_recs[["sku_id", "vendor_id"]].drop_duplicates().iterrows():
            vid = row["vendor_id"]
            if vid and pd.notna(vid):
                sku_vendor_map[row["sku_id"]].append(vid)

    # Step 3: Group needs by vendor
    vendor_needs: dict[str, list[dict]] = defaultdict(list)
    for _, row in replenishment_recs.iterrows():
        vid = row.get("vendor_id", "")
        if not vid or pd.isna(vid):
            continue

        is_new = row.get("lifecycle_stage", "") in ("new", "launch")
        lifecycle = row.get("lifecycle_stage", "active")

        # Select vendor(s) for this SKU
        allocations = select_vendor(
            row["sku_id"], scorecards, sku_vendor_map, config, is_new
        )

        qty = int(row.get("recommended_qty", 0))
        if qty <= 0:
            continue

        for alloc_vendor, alloc_pct in allocations:
            alloc_qty = max(1, int(qty * alloc_pct))
            vendor_needs[alloc_vendor].append({
                "sku_id": row["sku_id"],
                "qty": alloc_qty,
                "destination_store": row.get("destination_store", "warehouse"),
                "urgency": row.get("urgency", "normal"),
                "category": row.get("category", ""),
                "lifecycle_stage": lifecycle,
                "is_new_sku": is_new,
            })

    # Step 4: Generate POs per vendor
    recommendations = []
    total_units = 0
    total_value = 0.0
    skus_seen = set()
    split_count = 0

    for vendor_id, items in vendor_needs.items():
        sc = scorecards.get(vendor_id)
        if not sc:
            continue

        # Get vendor constraints
        vendor_row = vendor_data[vendor_data["vendor_id"] == vendor_id]
        moq = int(vendor_row.iloc[0].get("min_order_qty", 0)) if not vendor_row.empty else 0
        mov = float(vendor_row.iloc[0].get("min_order_value", 0)) if not vendor_row.empty else 0
        lead_time = int(vendor_row.iloc[0].get("avg_lead_time_days", 7)) if not vendor_row.empty else 7

        # Build PO lines
        lines = []
        po_qty = 0
        po_value = 0.0
        has_new = False
        max_urgency = "low"
        urgency_rank = {"emergency": 0, "urgent": 1, "normal": 2, "low": 3}

        for item in items:
            unit_cost = config.default_unit_cost
            line_qty = item["qty"]
            line_value = round(line_qty * unit_cost, 2)

            lines.append({
                "sku_id": item["sku_id"],
                "qty_ordered": line_qty,
                "unit_cost": unit_cost,
                "line_value": line_value,
                "destination_store": item["destination_store"],
                "urgency": item["urgency"],
                "is_new_sku": item["is_new_sku"],
                "lifecycle_stage": item["lifecycle_stage"],
            })
            po_qty += line_qty
            po_value += line_value
            skus_seen.add(item["sku_id"])

            if item["is_new_sku"]:
                has_new = True
            if urgency_rank.get(item["urgency"], 3) < urgency_rank.get(max_urgency, 3):
                max_urgency = item["urgency"]

        # Apply MOQ padding
        if config.pad_to_moq and moq > 0 and po_qty < moq:
            deficit = moq - po_qty
            if lines:
                lines[0]["qty_ordered"] += deficit
                lines[0]["line_value"] = round(lines[0]["qty_ordered"] * lines[0]["unit_cost"], 2)
                po_qty = sum(l["qty_ordered"] for l in lines)
                po_value = sum(l["line_value"] for l in lines)

        moq_met = po_qty >= moq if moq > 0 else True
        mov_met = po_value >= mov if mov > 0 else True

        po_id = f"PO-{vendor_id}-{order_date.isoformat()}-{len(recommendations):03d}"

        rec = PORecommendation(
            po_id=po_id,
            vendor_id=vendor_id,
            vendor_name=sc.vendor_name,
            vendor_tier=sc.tier,
            order_date=order_date.isoformat(),
            expected_delivery_date=(order_date + timedelta(days=lead_time)).isoformat(),
            lead_time_days=lead_time,
            lines=lines,
            total_qty=po_qty,
            total_value=round(po_value, 2),
            num_lines=len(lines),
            moq_met=moq_met,
            mov_met=mov_met,
            has_new_skus=has_new,
            urgency=max_urgency,
        )
        recommendations.append(rec)
        total_units += po_qty
        total_value += po_value

    # Diagnostics
    urgency_counts = defaultdict(int)
    for r in recommendations:
        urgency_counts[r.urgency] += 1

    diagnostics = {
        "vendors_used": len(set(r.vendor_id for r in recommendations)),
        "urgency_breakdown": dict(urgency_counts),
        "moq_issues": sum(1 for r in recommendations if not r.moq_met),
        "mov_issues": sum(1 for r in recommendations if not r.mov_met),
        "new_sku_pos": sum(1 for r in recommendations if r.has_new_skus),
        "split_orders": split_count,
    }

    logger.info(
        f"Generated {len(recommendations)} PO recommendations: "
        f"{total_units} units, ₹{total_value:,.0f} value, "
        f"{len(skus_seen)} SKUs, {diagnostics['vendors_used']} vendors"
    )

    return PORecommendationResult(
        recommendations=recommendations,
        total_pos=len(recommendations),
        total_units=total_units,
        total_value=round(total_value, 2),
        vendors_used=diagnostics["vendors_used"],
        skus_covered=len(skus_seen),
        split_orders=split_count,
        diagnostics=diagnostics,
    )
