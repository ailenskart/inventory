"""Assortment optimization API endpoints."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class AssortmentRecommendation(BaseModel):
    store_id: str
    cluster_id: str
    sku_id: str
    action: str  # add, remove, increase_display, reduce_display
    current_display_qty: int
    recommended_display_qty: int
    rationale: str


@router.get("/recommendations")
def get_assortment_recommendations(
    store_id: str | None = Query(None),
    cluster_id: str | None = Query(None),
):
    """Get assortment optimization recommendations for stores."""
    # TODO: Wire to services/assortment optimizer
    return {"recommendations": [], "store_count": 0}


@router.get("/clusters")
def get_store_clusters():
    """Get store cluster definitions and their assortment profiles."""
    # TODO: Return cluster analysis results
    return {"clusters": []}
