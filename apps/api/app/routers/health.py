"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "healthy", "service": "lenskart-retail-intelligence"}


@router.get("/ready")
def readiness_check():
    # TODO: Check DB connectivity, MLflow reachability
    return {"status": "ready"}
