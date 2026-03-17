"""Vendor schema."""

from schemas.base import TimestampMixin


class Vendor(TimestampMixin):
    vendor_id: str
    vendor_name: str
    vendor_type: str  # manufacturer, distributor
    contact_email: str | None = None
    contact_phone: str | None = None
    city: str | None = None
    state: str | None = None
    avg_lead_time_days: int = 7
    min_order_value: float = 0.0
    min_order_qty: int = 0
    reliability_score: float = 1.0  # 0-1
    is_active: bool = True
