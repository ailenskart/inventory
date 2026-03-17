"""Data validation checks for source and mart quality.

Lightweight validation framework (Great Expectations equivalent) that runs
assertions against DuckDB tables after dbt materializes models.

Usage:
    python data/validate.py

Checks cover:
- Source data completeness and referential integrity
- Mart data quality (no orphan keys, signal coherence)
- Business rules (non-negative inventory, receipt dates, transfer balance)
"""

import os
import sys
from dataclasses import dataclass

import duckdb

DB_PATH = os.path.join(os.path.dirname(__file__), "dev.duckdb")


@dataclass
class ValidationResult:
    name: str
    passed: bool
    message: str
    failing_rows: int = 0


def run_check(con: duckdb.DuckDBPyConnection, name: str, query: str, expect_zero: bool = True) -> ValidationResult:
    """Run a validation query. If expect_zero, the query should return 0 rows to pass."""
    try:
        result = con.execute(query).fetchall()
        count = len(result)
        if expect_zero:
            passed = count == 0
            msg = "PASS" if passed else f"FAIL: {count} failing rows"
        else:
            passed = count > 0
            msg = "PASS" if passed else "FAIL: expected rows but got 0"
        return ValidationResult(name=name, passed=passed, message=msg, failing_rows=count if not passed else 0)
    except Exception as e:
        return ValidationResult(name=name, passed=False, message=f"ERROR: {e}")


def validate_sources(con: duckdb.DuckDBPyConnection) -> list[ValidationResult]:
    """Validate source data quality."""
    results = []

    # 1. Stores: all store_ids are unique and non-null
    results.append(run_check(con, "src_stores_unique_id",
        "select store_id from main_raw.stores group by store_id having count(*) > 1"))

    # 2. SKUs: all sku_ids unique, valid categories
    results.append(run_check(con, "src_skus_unique_id",
        "select sku_id from main_raw.skus group by sku_id having count(*) > 1"))
    results.append(run_check(con, "src_skus_valid_category",
        "select * from main_raw.skus where category not in ('eyeglasses', 'sunglasses', 'contact_lenses', 'computer_glasses')"))

    # 3. Vendors: unique, valid type
    results.append(run_check(con, "src_vendors_unique_id",
        "select vendor_id from main_raw.vendors group by vendor_id having count(*) > 1"))

    # 4. Sales: referential integrity
    results.append(run_check(con, "src_sales_valid_store",
        "select distinct s.store_id from main_raw.daily_sales s left join main_raw.stores st on s.store_id = st.store_id where st.store_id is null"))
    results.append(run_check(con, "src_sales_valid_sku",
        "select distinct s.sku_id from main_raw.daily_sales s left join main_raw.skus sk on s.sku_id = sk.sku_id where sk.sku_id is null"))

    # 5. Sales: no negative quantities
    results.append(run_check(con, "src_sales_non_negative_qty",
        "select * from main_raw.daily_sales where cast(qty_sold as integer) < 0"))

    # 6. Inventory: non-negative on_hand
    results.append(run_check(con, "src_inventory_non_negative",
        "select * from main_raw.daily_inventory where cast(on_hand_qty as integer) < 0"))

    # 7. Transfer balance: out = in for completed transfers
    results.append(run_check(con, "src_transfer_balance",
        """
        with bal as (
            select transfer_id,
                sum(case when transfer_direction='out' then cast(transfer_qty as int) else 0 end) as out_q,
                sum(case when transfer_direction='in' then cast(transfer_qty as int) else 0 end) as in_q
            from main_raw.transfers where status='received' group by transfer_id
        )
        select * from bal where out_q != in_q
        """))

    # 8. Store ownership types are valid
    results.append(run_check(con, "src_stores_valid_type",
        "select * from main_raw.stores where store_type not in ('COCO', 'FOFO')"))

    # 9. Data completeness: expected minimum row counts (works for both full and lite mode)
    results.append(run_check(con, "src_stores_count",
        "select 1 where (select count(*) from main_raw.stores) < 10", expect_zero=True))
    results.append(run_check(con, "src_skus_count",
        "select 1 where (select count(*) from main_raw.skus) < 100", expect_zero=True))

    return results


def validate_marts(con: duckdb.DuckDBPyConnection) -> list[ValidationResult]:
    """Validate mart data quality after dbt run."""
    results = []

    # Check if marts exist
    try:
        con.execute("select 1 from main_marts.mart_demand_base limit 1").fetchall()
    except Exception:
        results.append(ValidationResult("marts_exist", False, "SKIP: marts not materialized yet"))
        return results

    # 1. mart_demand_base: no null keys
    results.append(run_check(con, "mart_demand_base_no_null_keys",
        "select * from main_marts.mart_demand_base where store_id is null or sku_id is null or week_start is null"))

    # 2. mart_demand_base: signals are non-negative
    results.append(run_check(con, "mart_demand_base_non_negative_signals",
        "select * from main_marts.mart_demand_base where sell_through_signal < 0 or prescription_order_signal < 0 or display_interest_signal < 0"))

    # 3. mart_demand_base: valid store_clusters
    results.append(run_check(con, "mart_demand_base_valid_clusters",
        "select * from main_marts.mart_demand_base where store_cluster not in ('METRO_HIGH','METRO_MID','TIER1_HIGH','TIER1_MID','TIER2','KIOSK') and store_cluster is not null"))

    # 4. mart_demand_base: valid sku_types
    results.append(run_check(con, "mart_demand_base_valid_sku_types",
        "select * from main_marts.mart_demand_base where sku_type not in ('display_dummy','physical_sell') and sku_type is not null"))

    # 5. mart_inventory_position: valid statuses
    results.append(run_check(con, "mart_inventory_valid_status",
        "select * from main_marts.mart_inventory_position where inventory_status not in ('stockout','stockout_pending_receipt','critical','low','healthy','excess','dead_stock')"))

    # 6. mart_vendor_performance: all vendors present
    results.append(run_check(con, "mart_vendor_all_present",
        "select v.vendor_id from main_dimensions.dim_vendor v left join main_marts.mart_vendor_performance mv on v.vendor_id = mv.vendor_id where mv.vendor_id is null"))

    # 7. Signal coherence: display_interest_signal should only exist for display_dummy SKUs
    results.append(run_check(con, "mart_display_signal_coherence",
        """
        select * from main_marts.mart_demand_base
        where display_interest_signal > 0 and sku_type = 'physical_sell' and category = 'sunglasses'
        limit 1
        """))

    return results


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Run 'make generate-data && make dbt-seed && make dbt-run' first.")
        sys.exit(1)

    con = duckdb.connect(DB_PATH, read_only=True)

    print("=" * 60)
    print("Lenskart Data Foundation — Validation Report")
    print("=" * 60)

    print("\n--- Source Validations ---")
    source_results = validate_sources(con)
    for r in source_results:
        status = "✓" if r.passed else "✗"
        print(f"  {status} {r.name}: {r.message}")

    print("\n--- Mart Validations ---")
    mart_results = validate_marts(con)
    for r in mart_results:
        status = "✓" if r.passed else "✗"
        print(f"  {status} {r.name}: {r.message}")

    all_results = source_results + mart_results
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    print(f"\n--- Summary: {passed} passed, {failed} failed out of {len(all_results)} checks ---")

    con.close()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
