"""Lenskart Retail Intelligence API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.routers import assortment, forecasts, health, lifecycle, purchase_orders, replenishment, transfers, vendors

app = FastAPI(
    title="Lenskart Retail Intelligence",
    description="Demand forecasting, assortment optimization, replenishment, and vendor collaboration APIs",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(forecasts.router, prefix="/api/v1/forecasts", tags=["Forecasts"])
app.include_router(replenishment.router, prefix="/api/v1/replenishment", tags=["Replenishment"])
app.include_router(assortment.router, prefix="/api/v1/assortment", tags=["Assortment"])
app.include_router(transfers.router, prefix="/api/v1/transfers", tags=["Transfers"])
app.include_router(vendors.router, prefix="/api/v1/vendors", tags=["Vendors"])
app.include_router(lifecycle.router, prefix="/api/v1/lifecycle", tags=["Lifecycle"])
app.include_router(purchase_orders.router, prefix="/api/v1/purchase-orders", tags=["Purchase Orders"])
