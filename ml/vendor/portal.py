"""Vendor portal payload schemas.

Defines the data structures shared with vendors through the portal:
- Forecast visibility: rolling demand forecasts by SKU
- Open PO status: current POs and their status
- Committed capacity: what the vendor has committed to deliver
"""

import logging
from dataclasses import dataclass, field
from datetime import date

logger = logging.getLogger(__name__)


@dataclass
class ForecastLine:
    """Single forecast line visible to vendor."""

    sku_id: str
    category: str
    total_forecast_qty: float
    store_count: int
    avg_forecast_per_store: float
    horizon_weeks: int


@dataclass
class OpenPOLine:
    """Open PO line visible to vendor."""

    po_id: str
    sku_id: str
    qty_ordered: int
    qty_received: int
    status: str  # draft, submitted, approved, in_transit, received
    order_date: str
    expected_delivery_date: str
    is_overdue: bool


@dataclass
class CapacityCommitment:
    """Vendor's committed capacity for a period."""

    period_start: str
    period_end: str
    status: str  # confirmed, forecast
    total_qty: int
    total_value: float
    sku_count: int


@dataclass
class VendorPortalPayload:
    """Complete vendor portal payload."""

    vendor_id: str
    vendor_name: str
    generated_date: str

    # Forecast visibility
    forecast_horizon_weeks: int
    forecast_lines: list[ForecastLine] = field(default_factory=list)
    total_forecast_units: float = 0.0

    # Open PO status
    open_pos: list[OpenPOLine] = field(default_factory=list)
    total_open_qty: int = 0
    overdue_count: int = 0

    # Committed capacity
    capacity_commitments: list[CapacityCommitment] = field(default_factory=list)
    total_committed_qty: int = 0
    total_committed_value: float = 0.0


def build_vendor_portal_payload(
    vendor_id: str,
    vendor_name: str,
    forecast_data: list[dict] | None = None,
    open_po_data: list[dict] | None = None,
    capacity_data: list[dict] | None = None,
    horizon_weeks: int = 12,
    as_of_date: date | None = None,
) -> VendorPortalPayload:
    """Build the vendor portal payload from available data sources.

    This is the main entry point for generating vendor-facing data.
    """
    if as_of_date is None:
        as_of_date = date.today()

    # Build forecast lines
    forecast_lines = []
    total_forecast = 0.0
    if forecast_data:
        for fd in forecast_data:
            fl = ForecastLine(
                sku_id=fd.get("sku_id", ""),
                category=fd.get("category", ""),
                total_forecast_qty=float(fd.get("total_forecast_qty", 0)),
                store_count=int(fd.get("store_count", 0)),
                avg_forecast_per_store=float(fd.get("avg_forecast_per_store", 0)),
                horizon_weeks=horizon_weeks,
            )
            forecast_lines.append(fl)
            total_forecast += fl.total_forecast_qty

    # Build open PO lines
    open_pos = []
    total_open_qty = 0
    overdue_count = 0
    if open_po_data:
        for po in open_po_data:
            expected = po.get("expected_delivery_date", "")
            is_overdue = False
            if expected and po.get("status") not in ("received", "cancelled"):
                try:
                    exp_date = date.fromisoformat(str(expected))
                    is_overdue = exp_date < as_of_date
                except (ValueError, TypeError):
                    pass

            opl = OpenPOLine(
                po_id=po.get("po_id", ""),
                sku_id=po.get("sku_id", ""),
                qty_ordered=int(po.get("qty_ordered", po.get("total_qty", 0))),
                qty_received=int(po.get("qty_received", 0)),
                status=po.get("status", "unknown"),
                order_date=str(po.get("order_date", "")),
                expected_delivery_date=str(expected),
                is_overdue=is_overdue,
            )
            open_pos.append(opl)
            if opl.status not in ("received", "cancelled"):
                total_open_qty += opl.qty_ordered
            if is_overdue:
                overdue_count += 1

    # Build capacity commitments
    commitments = []
    total_committed_qty = 0
    total_committed_value = 0.0
    if capacity_data:
        for cd in capacity_data:
            cc = CapacityCommitment(
                period_start=str(cd.get("period_start", "")),
                period_end=str(cd.get("period_end", "")),
                status=cd.get("status", "forecast"),
                total_qty=int(cd.get("total_qty", 0)),
                total_value=float(cd.get("total_value", 0)),
                sku_count=int(cd.get("sku_count", len(cd.get("lines", [])))),
            )
            commitments.append(cc)
            total_committed_qty += cc.total_qty
            total_committed_value += cc.total_value

    return VendorPortalPayload(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        generated_date=as_of_date.isoformat(),
        forecast_horizon_weeks=horizon_weeks,
        forecast_lines=forecast_lines,
        total_forecast_units=round(total_forecast, 0),
        open_pos=open_pos,
        total_open_qty=total_open_qty,
        overdue_count=overdue_count,
        capacity_commitments=commitments,
        total_committed_qty=total_committed_qty,
        total_committed_value=round(total_committed_value, 2),
    )
