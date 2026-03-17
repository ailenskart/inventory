"""Lenskart Retail Intelligence API.

Unified API layer exposing all platform capabilities:
- Demand forecasting
- Product lifecycle intelligence
- Assortment optimization
- Replenishment automation
- Inter-store transfer optimization
- Vendor intelligence & purchase orders
- Control tower (unified summary)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.routers import (
    assortment,
    control_tower,
    forecasts,
    health,
    lifecycle,
    purchase_orders,
    replenishment,
    transfers,
    vendors,
)

app = FastAPI(
    title="Lenskart Retail Intelligence",
    description=(
        "Unified retail intelligence platform: demand forecasting, "
        "lifecycle classification, assortment optimization, replenishment, "
        "transfer optimization, vendor intelligence, and purchase order management."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health
app.include_router(health.router)

# Control tower (unified view)
app.include_router(control_tower.router, prefix="/api/v1/control-tower", tags=["Control Tower"])

# Domain APIs
app.include_router(forecasts.router, prefix="/api/v1/forecasts", tags=["Forecasts"])
app.include_router(lifecycle.router, prefix="/api/v1/lifecycle", tags=["Lifecycle"])
app.include_router(replenishment.router, prefix="/api/v1/replenishment", tags=["Replenishment"])
app.include_router(assortment.router, prefix="/api/v1/assortment", tags=["Assortment"])
app.include_router(transfers.router, prefix="/api/v1/transfers", tags=["Transfers"])
app.include_router(vendors.router, prefix="/api/v1/vendors", tags=["Vendors"])
app.include_router(purchase_orders.router, prefix="/api/v1/purchase-orders", tags=["Purchase Orders"])
