"""Customer signal schemas: trials, eye tests, traffic."""

from datetime import date, datetime

from pydantic import BaseModel


class StoreTrial(BaseModel):
    """Try-on event at store - key demand signal for display frames."""
    trial_id: str
    store_id: str
    sku_id: str
    trial_date: date
    trial_time: datetime | None = None
    customer_id: str | None = None
    resulted_in_order: bool = False
    order_id: str | None = None


class EyeTest(BaseModel):
    """Prescription capture at store."""
    test_id: str
    store_id: str
    test_date: date
    customer_id: str | None = None
    sph_right: float | None = None
    cyl_right: float | None = None
    sph_left: float | None = None
    cyl_left: float | None = None
    resulted_in_purchase: bool = False
    order_id: str | None = None


class StoreTraffic(BaseModel):
    """Daily footfall / traffic count per store."""
    store_id: str
    traffic_date: date
    footfall_count: int = 0
    walk_ins: int = 0
    appointments: int = 0


class PricingPromotion(BaseModel):
    """Pricing and promotional events."""
    promo_id: str
    sku_id: str | None = None  # None = store-wide
    store_id: str | None = None  # None = all stores
    start_date: date
    end_date: date
    promo_type: str  # discount, bogo, bundle, clearance
    discount_pct: float = 0.0
    discount_value: float = 0.0
    is_active: bool = True
