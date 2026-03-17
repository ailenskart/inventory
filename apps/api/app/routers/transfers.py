"""Inter-store transfer API endpoints.

POST /transfers/run      — trigger transfer optimization pipeline
GET  /transfers/store/{store_id} — get transfers for a store (inbound + outbound)
GET  /transfers/recommendations  — list all current transfer recommendations
GET  /transfers/simulation       — run greedy-vs-optimized simulation
POST /transfers/execute          — approve and initiate selected transfers
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()

DB_PATH = "data/dev.duckdb"


# ─── Request / Response models ────────────────────────────────────────────────


class TransferRunRequest(BaseModel):
    min_source_wos: float = Field(8.0, description="Min weeks-of-supply at source")
    max_destination_wos: float = Field(3.0, description="Max weeks-of-supply at destination")
    frequency: str = Field("weekly", description="Run frequency: daily or weekly")
    cost_per_unit: float = Field(50.0, description="Variable cost per unit transferred (₹)")


class TransferRunResponse(BaseModel):
    status: str
    selected_transfers: int
    total_units: int
    total_recovered_value: float
    total_transfer_cost: float
    net_value: float
    solve_time_ms: float
    summary: dict


class TransferRecommendation(BaseModel):
    transfer_id: str
    from_store_id: str
    to_store_id: str
    sku_id: str
    qty: int
    reason: str
    transfer_lead_time_days: int
    recovered_value: float
    transfer_cost: float
    net_value: float
    lifecycle_stage: str
    source_wos_before: float
    destination_wos_before: float


class StoreTransfersResponse(BaseModel):
    store_id: str
    outbound: list[dict]
    inbound: list[dict]
    total_outbound_units: int
    total_inbound_units: int
    net_units: int


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/run", response_model=TransferRunResponse)
def trigger_transfer_run(request: TransferRunRequest):
    """Run the inter-store transfer optimization pipeline."""
    from services.transfers.config import TransferConfig
    from services.transfers.pipeline import run_transfer_pipeline

    config = TransferConfig(
        db_path=DB_PATH,
        min_source_wos=request.min_source_wos,
        max_destination_wos=request.max_destination_wos,
        run_frequency=request.frequency,
        cost_per_unit=request.cost_per_unit,
    )

    try:
        result = run_transfer_pipeline(config, write_to_db=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return TransferRunResponse(
        status=result.status,
        selected_transfers=result.selected_transfers,
        total_units=result.total_units,
        total_recovered_value=result.total_recovered_value,
        total_transfer_cost=result.total_transfer_cost,
        net_value=result.net_value,
        solve_time_ms=result.solve_time_ms,
        summary={
            "source_stores_relieved": len(result.source_relief),
            "diagnostics": result.diagnostics,
            "source_relief": result.source_relief,
        },
    )


@router.get("/store/{store_id}", response_model=StoreTransfersResponse)
def get_store_transfers(store_id: str):
    """Get transfer recommendations for a specific store (inbound and outbound)."""
    import duckdb

    from services.transfers.config import TransferConfig

    config = TransferConfig(db_path=DB_PATH)

    try:
        con = duckdb.connect(config.db_path, read_only=True)
        con.execute(f"SELECT 1 FROM {config.output_table} LIMIT 1")  # noqa: S608
    except Exception:
        try:
            con.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=404,
            detail=f"No transfer recommendations found. Run POST /transfers/run first.",
        )

    outbound_df = con.execute(f"""
        SELECT * FROM {config.output_table}
        WHERE from_store_id = ?
    """, [store_id]).fetchdf()  # noqa: S608

    inbound_df = con.execute(f"""
        SELECT * FROM {config.output_table}
        WHERE to_store_id = ?
    """, [store_id]).fetchdf()  # noqa: S608

    con.close()

    if outbound_df.empty and inbound_df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No transfers found for store {store_id}",
        )

    outbound = outbound_df.to_dict(orient="records") if not outbound_df.empty else []
    inbound = inbound_df.to_dict(orient="records") if not inbound_df.empty else []

    total_out = int(outbound_df["qty"].sum()) if not outbound_df.empty else 0
    total_in = int(inbound_df["qty"].sum()) if not inbound_df.empty else 0

    return StoreTransfersResponse(
        store_id=store_id,
        outbound=outbound,
        inbound=inbound,
        total_outbound_units=total_out,
        total_inbound_units=total_in,
        net_units=total_in - total_out,
    )


@router.get("/recommendations")
def get_transfer_recommendations(
    reason: str | None = Query(None, description="Filter by reason code"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get all current transfer recommendations."""
    import duckdb

    from services.transfers.config import TransferConfig

    config = TransferConfig(db_path=DB_PATH)

    try:
        con = duckdb.connect(config.db_path, read_only=True)
        con.execute(f"SELECT 1 FROM {config.output_table} LIMIT 1")  # noqa: S608
    except Exception:
        try:
            con.close()
        except Exception:
            pass
        return {"transfers": [], "total_units": 0, "estimated_impact": 0.0}

    query = f"SELECT * FROM {config.output_table}"  # noqa: S608
    params = []
    if reason:
        query += " WHERE reason = ?"
        params.append(reason)
    query += f" ORDER BY net_value DESC LIMIT {limit}"

    df = con.execute(query, params).fetchdf()
    con.close()

    transfers = df.to_dict(orient="records") if not df.empty else []
    total_units = int(df["qty"].sum()) if not df.empty else 0
    estimated_impact = float(df["net_value"].sum()) if not df.empty else 0.0

    return {
        "transfers": transfers,
        "total_units": total_units,
        "estimated_impact": estimated_impact,
        "count": len(transfers),
    }


@router.get("/simulation")
def run_transfer_simulation(
    n_stores: int = Query(20, ge=2, le=100),
    n_skus: int = Query(50, ge=5, le=500),
    seed: int = Query(42),
):
    """Run a simulation comparing greedy vs optimized transfer selection."""
    from services.transfers.simulation import run_simulation

    try:
        result = run_simulation(n_stores=n_stores, n_skus=n_skus, seed=seed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result


@router.post("/execute")
def execute_transfers(transfer_ids: list[str]):
    """Approve and initiate selected transfers."""
    # TODO: Wire to execution engine / WMS integration
    return {
        "status": "accepted",
        "transfers_initiated": len(transfer_ids),
        "transfer_ids": transfer_ids,
    }
