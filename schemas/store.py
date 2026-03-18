"""Store schema."""

from pydantic import BaseModel

from schemas.base import StoreFormat, StoreType, TimestampMixin


class Store(TimestampMixin):
    store_id: str
    store_name: str
    city: str
    state: str
    region: str
    pincode: str
    store_type: StoreType
    store_format: StoreFormat
    cluster_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    opening_date: str | None = None
    is_active: bool = True
    display_capacity: int = 0  # Number of display slots
    storage_capacity: int = 0  # Back-storage units
