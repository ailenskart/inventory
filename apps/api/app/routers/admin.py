"""Admin API router for data management, uploads, and pipeline control.

Provides endpoints for:
- CSV file upload (stores, SKUs, inventory, sales, etc.)
- Product catalog browsing & management
- Data seeding (populate demo data)
- Pipeline execution (forecasting, replenishment, etc.)
- Database table inspection
"""

import csv
import io
import logging
import os
from typing import Optional

import duckdb
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

DB_PATH = os.environ.get("DB_PATH", "data/dev.duckdb")


def _get_db(read_only: bool = True):
    return duckdb.connect(DB_PATH, read_only=read_only)


# ── Table browsing ────────────────────────────────────────────────────────────


@router.get("/tables")
def list_tables():
    """List all tables with row counts."""
    con = _get_db()
    rows = con.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema LIKE 'main%' ORDER BY 1, 2"
    ).fetchall()
    result = []
    for schema, table in rows:
        count = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]
        result.append({"schema": schema, "table": table, "rows": count})
    con.close()
    return {"tables": result, "count": len(result)}


@router.get("/tables/{schema}/{table}")
def browse_table(
    schema: str,
    table: str,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    """Browse a table with pagination."""
    con = _get_db()
    try:
        rows = con.execute(
            f'SELECT * FROM "{schema}"."{table}" LIMIT {limit} OFFSET {offset}'
        ).fetchdf()
        total = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]
        columns = list(rows.columns)
        data = rows.to_dict(orient="records")
    except Exception as e:
        con.close()
        raise HTTPException(status_code=404, detail=str(e))
    con.close()
    return {"columns": columns, "data": data, "total": total, "limit": limit, "offset": offset}


# ── Product catalog ───────────────────────────────────────────────────────────


@router.get("/catalog/products")
def list_products(
    category: Optional[str] = None,
    brand: Optional[str] = None,
    limit: int = Query(100, le=1000),
):
    """Browse product catalog (SKUs)."""
    con = _get_db()
    query = "SELECT * FROM main_dimensions.dim_sku WHERE 1=1"
    if category:
        query += f" AND category = '{category}'"
    if brand:
        query += f" AND brand = '{brand}'"
    query += f" LIMIT {limit}"
    try:
        rows = con.execute(query).fetchdf()
        data = rows.to_dict(orient="records")
    except Exception as e:
        con.close()
        raise HTTPException(status_code=500, detail=str(e))
    con.close()
    return {"products": data, "count": len(data)}


@router.get("/catalog/stores")
def list_stores(limit: int = Query(100, le=500)):
    """Browse store directory."""
    con = _get_db()
    try:
        rows = con.execute(f"SELECT * FROM main_dimensions.dim_store LIMIT {limit}").fetchdf()
        data = rows.to_dict(orient="records")
    except Exception as e:
        con.close()
        raise HTTPException(status_code=500, detail=str(e))
    con.close()
    return {"stores": data, "count": len(data)}


@router.get("/catalog/vendors")
def list_vendors():
    """Browse vendor directory."""
    con = _get_db()
    try:
        rows = con.execute("SELECT * FROM main_dimensions.dim_vendor").fetchdf()
        data = rows.to_dict(orient="records")
    except Exception as e:
        con.close()
        raise HTTPException(status_code=500, detail=str(e))
    con.close()
    return {"vendors": data, "count": len(data)}


@router.get("/catalog/stats")
def catalog_stats():
    """Get catalog summary statistics."""
    con = _get_db()
    stats = {}
    try:
        # SKU stats
        r = con.execute(
            "SELECT COUNT(*) as total, COUNT(DISTINCT category) as categories, "
            "COUNT(DISTINCT brand) as brands, AVG(mrp) as avg_mrp "
            "FROM main_dimensions.dim_sku"
        ).fetchone()
        stats["skus"] = {"total": r[0], "categories": r[1], "brands": r[2], "avg_mrp": round(r[3] or 0, 0)}

        # Category breakdown
        rows = con.execute(
            "SELECT category, COUNT(*) as count FROM main_dimensions.dim_sku GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        stats["category_breakdown"] = {r[0]: r[1] for r in rows}

        # Brand breakdown
        rows = con.execute(
            "SELECT brand, COUNT(*) as count FROM main_dimensions.dim_sku GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        stats["brand_breakdown"] = {r[0]: r[1] for r in rows}

        # Store stats
        r = con.execute(
            "SELECT COUNT(*) as total, COUNT(DISTINCT city) as cities, COUNT(DISTINCT region) as regions "
            "FROM main_dimensions.dim_store"
        ).fetchone()
        stats["stores"] = {"total": r[0], "cities": r[1], "regions": r[2]}

        # Vendor stats
        r = con.execute("SELECT COUNT(*) FROM main_dimensions.dim_vendor").fetchone()
        stats["vendors"] = {"total": r[0]}

        # Inventory stats
        r = con.execute(
            "SELECT COUNT(*) as positions, SUM(on_hand_qty) as total_on_hand, "
            "COUNT(DISTINCT store_id) as stores, COUNT(DISTINCT sku_id) as skus "
            "FROM main_marts.mart_inventory_position"
        ).fetchone()
        stats["inventory"] = {
            "positions": r[0], "total_on_hand": int(r[1] or 0),
            "stores": r[2], "skus": r[3],
        }

        # Sales stats
        r = con.execute(
            "SELECT COUNT(*) as transactions, SUM(total_qty_sold) as units_sold "
            "FROM main_marts.mart_demand_base"
        ).fetchone()
        stats["sales"] = {"weekly_records": r[0], "total_units_sold": int(r[1] or 0)}

    except Exception as e:
        stats["error"] = str(e)
    con.close()
    return stats


# ── CSV Upload ────────────────────────────────────────────────────────────────


UPLOAD_TABLES = {
    "stores": {"schema": "main_raw", "table": "stores"},
    "skus": {"schema": "main_raw", "table": "skus"},
    "daily_sales": {"schema": "main_raw", "table": "daily_sales"},
    "daily_inventory": {"schema": "main_raw", "table": "daily_inventory"},
    "purchase_orders": {"schema": "main_raw", "table": "purchase_orders"},
    "vendors": {"schema": "main_raw", "table": "vendors"},
    "transfers": {"schema": "main_raw", "table": "transfers"},
    "store_traffic": {"schema": "main_raw", "table": "store_traffic"},
    "receipts": {"schema": "main_raw", "table": "receipts"},
    "store_trials": {"schema": "main_raw", "table": "store_trials"},
    "eye_tests": {"schema": "main_raw", "table": "eye_tests"},
    "promotions": {"schema": "main_raw", "table": "promotions"},
    "calendar": {"schema": "main_raw", "table": "calendar"},
}


@router.get("/upload/targets")
def upload_targets():
    """List available upload targets with expected columns."""
    con = _get_db()
    targets = []
    for name, info in UPLOAD_TABLES.items():
        try:
            cols = con.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema = '{info['schema']}' AND table_name = '{info['table']}' "
                f"ORDER BY ordinal_position"
            ).fetchall()
            targets.append({
                "name": name,
                "schema": info["schema"],
                "table": info["table"],
                "columns": [c[0] for c in cols],
            })
        except Exception:
            targets.append({"name": name, "schema": info["schema"], "table": info["table"], "columns": []})
    con.close()
    return {"targets": targets}


@router.post("/upload/{target}")
async def upload_csv(target: str, file: UploadFile = File(...), mode: str = Query("append", pattern="^(append|replace)$")):
    """Upload a CSV file to a raw table.

    Args:
        target: Table target name (e.g. 'stores', 'skus', 'daily_sales')
        file: CSV file to upload
        mode: 'append' to add rows, 'replace' to replace all data
    """
    if target not in UPLOAD_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown target: {target}. Valid: {list(UPLOAD_TABLES.keys())}")

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    info = UPLOAD_TABLES[target]
    schema, table = info["schema"], info["table"]

    content = await file.read()
    text = content.decode("utf-8")

    # Parse CSV
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    con = _get_db(read_only=False)
    try:
        import pandas as pd
        df = pd.DataFrame(rows)

        if mode == "replace":
            con.execute(f'DROP TABLE IF EXISTS "{schema}"."{table}"')
            con.execute(f'CREATE TABLE "{schema}"."{table}" AS SELECT * FROM df')
        else:
            con.execute(f'INSERT INTO "{schema}"."{table}" SELECT * FROM df')

        count = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]
    except Exception as e:
        con.close()
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    con.close()

    return {
        "status": "success",
        "target": target,
        "rows_uploaded": len(rows),
        "total_rows": count,
        "mode": mode,
    }


# ── Pipeline control ─────────────────────────────────────────────────────────


class PipelineRequest(BaseModel):
    """Request to run a specific pipeline."""
    pass


@router.post("/pipeline/seed-demo")
def seed_demo_data():
    """Seed demo data into ML tables (forecasts, replenishment, transfers, POs).

    This creates realistic demo data directly so the dashboard shows populated results.
    """
    import random
    from datetime import date, timedelta

    import pandas as pd

    random.seed(42)
    con = _get_db(read_only=False)
    con.execute("CREATE SCHEMA IF NOT EXISTS main_ml")
    results = {}

    try:
        # Get store and SKU IDs
        stores = [r[0] for r in con.execute("SELECT store_id FROM main_dimensions.dim_store").fetchall()]
        skus_df = con.execute(
            "SELECT sku_id, category, brand, mrp FROM main_dimensions.dim_sku"
        ).fetchdf()
        sku_ids = skus_df["sku_id"].tolist()
        vendors = [r[0] for r in con.execute("SELECT vendor_id FROM main_dimensions.dim_vendor").fetchall()]

        # ── 1. Demand Forecasts ──────────────────────────────────
        logger.info("Seeding demand forecasts...")
        forecast_rows = []
        today = date.today()
        models = ["Ensemble", "AutoETS", "SeasonalNaive"]
        for store in stores:
            sample_skus = random.sample(sku_ids, min(80, len(sku_ids)))
            for sku in sample_skus:
                base = random.uniform(1, 25)
                for w in range(1, 5):
                    week = today + timedelta(weeks=w)
                    point = round(max(0, base + random.gauss(0, base * 0.2)), 1)
                    forecast_rows.append({
                        "store_id": store,
                        "sku_id": sku,
                        "forecast_week": str(week),
                        "point_forecast": point,
                        "lower_bound": round(max(0, point * 0.7), 1),
                        "upper_bound": round(point * 1.3, 1),
                        "model_used": random.choice(models),
                        "model_version": "v1.0",
                        "reason_code": "standard_forecast",
                        "forecast_date": str(today),
                    })

        df_fc = pd.DataFrame(forecast_rows)
        con.execute("DROP TABLE IF EXISTS main_ml.demand_forecasts")
        con.execute("CREATE TABLE main_ml.demand_forecasts AS SELECT * FROM df_fc")
        results["forecasts"] = len(forecast_rows)

        # ── 2. Replenishment Recommendations ─────────────────────
        logger.info("Seeding replenishment recommendations...")
        replen_rows = []
        urgencies = ["emergency", "urgent", "normal", "normal", "normal"]
        reason_codes = ["below_reorder_point", "stockout_imminent", "safety_stock_breach", "forecast_driven"]
        for store in stores:
            n_recs = random.randint(5, 30)
            for sku in random.sample(sku_ids, min(n_recs, len(sku_ids))):
                sku_info = skus_df[skus_df["sku_id"] == sku].iloc[0]
                urgency = random.choice(urgencies)
                on_hand = random.randint(0, 8)
                reorder = random.uniform(5, 20)
                replen_rows.append({
                    "sku_id": sku,
                    "destination_store": store,
                    "source_location": random.choice(["DC_MUMBAI", "DC_DELHI", "DC_BANGALORE"]),
                    "recommended_qty": random.randint(3, 30),
                    "urgency": urgency,
                    "reason_code": random.choice(reason_codes),
                    "reason_description": f"Reorder needed — {urgency} level",
                    "on_hand_qty": on_hand,
                    "in_transit_qty": random.randint(0, 5),
                    "reorder_point": round(reorder, 1),
                    "safety_stock": round(reorder * 0.5, 1),
                    "current_days_of_cover": round(on_hand / max(random.uniform(0.5, 3), 0.1), 1),
                    "expected_days_of_cover_after": round(random.uniform(14, 45), 1),
                    "stockout_risk": round(random.uniform(0.3, 0.95) if urgency != "normal" else random.uniform(0.05, 0.3), 2),
                    "lost_sales_estimate": round(random.uniform(500, 8000), 0),
                    "category": sku_info["category"],
                    "vendor_id": random.choice(vendors),
                })

        df_rep = pd.DataFrame(replen_rows)
        con.execute("DROP TABLE IF EXISTS main_ml.replenishment_recommendations")
        con.execute("CREATE TABLE main_ml.replenishment_recommendations AS SELECT * FROM df_rep")
        results["replenishment"] = len(replen_rows)

        # ── 3. Transfer Recommendations ──────────────────────────
        logger.info("Seeding transfer recommendations...")
        transfer_rows = []
        reasons = ["excess_to_deficit", "lifecycle_rebalance", "regional_demand_shift", "slow_mover_rescue"]
        for _ in range(min(200, len(stores) * 4)):
            from_store, to_store = random.sample(stores, 2)
            sku = random.choice(sku_ids)
            qty = random.randint(2, 15)
            unit_val = random.uniform(800, 5000)
            transfer_rows.append({
                "transfer_id": f"TRF{random.randint(10000, 99999)}",
                "from_store_id": from_store,
                "to_store_id": to_store,
                "sku_id": sku,
                "qty": qty,
                "reason": random.choice(reasons),
                "transfer_lead_time_days": random.randint(1, 5),
                "recovered_value": round(qty * unit_val, 2),
                "transfer_cost": round(qty * random.uniform(30, 100), 2),
                "net_value": round(qty * (unit_val - random.uniform(30, 100)), 2),
                "lifecycle_stage": random.choice(["core", "growth", "maturity", "decline"]),
                "source_wos_before": round(random.uniform(6, 20), 1),
                "destination_wos_before": round(random.uniform(0.5, 3), 1),
            })

        df_tr = pd.DataFrame(transfer_rows)
        con.execute("DROP TABLE IF EXISTS main_ml.transfer_recommendations")
        con.execute("CREATE TABLE main_ml.transfer_recommendations AS SELECT * FROM df_tr")
        results["transfers"] = len(transfer_rows)

        # ── 4. PO Recommendations ────────────────────────────────
        logger.info("Seeding PO recommendations...")
        po_rows = []
        statuses = ["draft", "submitted", "approved", "in_transit", "received"]
        for vendor in vendors:
            n_pos = random.randint(5, 15)
            for i in range(n_pos):
                po_id = f"PO-{vendor}-{random.randint(1000, 9999)}"
                n_lines = random.randint(3, 12)
                for _ in range(n_lines):
                    sku = random.choice(sku_ids)
                    qty = random.randint(10, 200)
                    unit_cost = random.uniform(200, 3000)
                    po_rows.append({
                        "po_id": po_id,
                        "vendor_id": vendor,
                        "sku_id": sku,
                        "qty_ordered": qty,
                        "unit_cost": round(unit_cost, 2),
                        "line_value": round(qty * unit_cost, 2),
                        "urgency": random.choice(["high", "medium", "low"]),
                        "status": random.choice(statuses),
                        "order_date": str(today - timedelta(days=random.randint(1, 30))),
                        "expected_delivery_date": str(today + timedelta(days=random.randint(3, 21))),
                    })

        df_po = pd.DataFrame(po_rows)
        con.execute("DROP TABLE IF EXISTS main_ml.po_recommendations")
        con.execute("CREATE TABLE main_ml.po_recommendations AS SELECT * FROM df_po")
        results["purchase_orders"] = len(po_rows)

    except Exception as e:
        con.close()
        raise HTTPException(status_code=500, detail=f"Seeding failed: {e}")

    con.close()
    return {"status": "success", "seeded": results}


@router.post("/pipeline/run-forecasting")
def run_forecasting():
    """Trigger the demand forecasting pipeline."""
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))
    try:
        from ml.forecasting.config import ForecastConfig
        from ml.forecasting.predict import run_inference_pipeline
        from ml.forecasting.train import run_training_pipeline

        config = ForecastConfig(db_path=DB_PATH)
        run_training_pipeline(config)
        forecasts = run_inference_pipeline(config, write_to_db=True)
        return {"status": "success", "rows": len(forecasts), "stores": int(forecasts["store_id"].nunique()) if not forecasts.empty else 0}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/pipeline/run-replenishment")
def run_replenishment():
    """Trigger the replenishment pipeline."""
    try:
        from services.replenishment.config import ReplenishmentConfig
        from services.replenishment.pipeline import run_replenishment_pipeline
        config = ReplenishmentConfig(db_path=DB_PATH)
        recs = run_replenishment_pipeline(config, write_to_db=True)
        return {"status": "success", "recommendations": len(recs)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/pipeline/run-transfers")
def run_transfers():
    """Trigger the transfer optimization pipeline."""
    try:
        from services.transfers.config import TransferConfig
        from services.transfers.pipeline import run_transfer_pipeline
        config = TransferConfig(db_path=DB_PATH)
        result = run_transfer_pipeline(config, write_to_db=True)
        return {"status": "success", "transfers": result.selected_transfers, "net_value": result.net_value}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/pipeline/run-lifecycle")
def run_lifecycle():
    """Trigger the lifecycle classification pipeline."""
    try:
        from services.lifecycle.config import LifecycleConfig
        from services.lifecycle.pipeline import run_lifecycle_pipeline
        config = LifecycleConfig(db_path=DB_PATH)
        classifications, _ = run_lifecycle_pipeline(config, include_v2_scoring=True, write_to_db=True)
        return {"status": "success", "classified": len(classifications)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/pipeline/run-all")
def run_all_pipelines():
    """Run all ML pipelines in sequence."""
    results = {}
    for name, func in [
        ("lifecycle", run_lifecycle),
        ("forecasting", run_forecasting),
        ("replenishment", run_replenishment),
        ("transfers", run_transfers),
    ]:
        try:
            results[name] = func()
        except Exception as e:
            results[name] = {"status": "error", "detail": str(e)}
    return {"status": "complete", "results": results}


@router.post("/pipeline/refresh-dbt")
def refresh_dbt():
    """Re-run dbt transformations (staging → dimensions → marts)."""
    import subprocess
    dbt_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "transform", "dbt")
    dbt_dir = os.path.normpath(dbt_dir)
    try:
        result = subprocess.run(
            ["dbt", "run", "--profiles-dir", "."],
            cwd=dbt_dir, capture_output=True, text=True, timeout=300,
        )
        return {
            "status": "success" if result.returncode == 0 else "error",
            "output": result.stdout[-2000:] if result.stdout else "",
            "errors": result.stderr[-1000:] if result.stderr else "",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ── Data export ───────────────────────────────────────────────────────────────


@router.get("/export/{schema}/{table}")
def export_table(schema: str, table: str, format: str = Query("json", pattern="^(json|csv)$")):
    """Export a table as JSON or CSV."""
    con = _get_db()
    try:
        df = con.execute(f'SELECT * FROM "{schema}"."{table}"').fetchdf()
    except Exception as e:
        con.close()
        raise HTTPException(status_code=404, detail=str(e))
    con.close()

    if format == "csv":
        from fastapi.responses import StreamingResponse
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        stream.seek(0)
        return StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={schema}_{table}.csv"},
        )
    return {"data": df.to_dict(orient="records"), "count": len(df)}
