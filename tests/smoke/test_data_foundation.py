"""End-to-end smoke test for the data foundation pipeline.

Runs the complete pipeline:
1. Generate synthetic data
2. Copy to dbt seeds
3. Run dbt seed (load into DuckDB)
4. Run dbt models (staging → dimensions → intermediate → marts)
5. Run dbt tests
6. Run data validation
7. Assert mart contents

This test requires dbt-core and dbt-duckdb to be installed.
"""

import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DBT_DIR = os.path.join(PROJECT_ROOT, "transform", "dbt")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "dev.duckdb")


def run_cmd(cmd: list[str], cwd: str = PROJECT_ROOT) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)


def has_dbt():
    """Check if dbt is available."""
    try:
        result = subprocess.run(["dbt", "--version"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def has_duckdb():
    """Check if duckdb python package is available."""
    try:
        import duckdb  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.smoke
class TestDataFoundationPipeline:
    """End-to-end smoke test for the data foundation."""

    @pytest.fixture(scope="class", autouse=True)
    def run_pipeline(self):
        """Run the full pipeline once for all tests in this class."""
        if not has_dbt():
            pytest.skip("dbt not installed")
        if not has_duckdb():
            pytest.skip("duckdb not installed")

        # Step 1: Generate synthetic data
        result = run_cmd([sys.executable, "data/synthetic/generate.py"])
        assert result.returncode == 0, f"Data generation failed:\n{result.stderr}"

        # Step 2: Copy seeds
        result = run_cmd([sys.executable, "data/load_seeds.py"])
        assert result.returncode == 0, f"Seed loading failed:\n{result.stderr}"

        # Step 3: dbt seed
        result = run_cmd(["dbt", "seed", "--profiles-dir", ".", "--full-refresh"], cwd=DBT_DIR)
        assert result.returncode == 0, f"dbt seed failed:\n{result.stderr}\n{result.stdout}"

        # Step 4: dbt run
        result = run_cmd(["dbt", "run", "--profiles-dir", "."], cwd=DBT_DIR)
        assert result.returncode == 0, f"dbt run failed:\n{result.stderr}\n{result.stdout}"

        # Step 5: dbt test
        result = run_cmd(["dbt", "test", "--profiles-dir", "."], cwd=DBT_DIR)
        assert result.returncode == 0, f"dbt test failed:\n{result.stderr}\n{result.stdout}"

    def test_duckdb_exists(self):
        """DuckDB file was created."""
        assert os.path.exists(DB_PATH), f"DuckDB not found at {DB_PATH}"

    def test_dim_store_row_count(self):
        """dim_store should have 50 rows."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_dimensions.dim_store").fetchone()[0]
        con.close()
        assert count == 50, f"Expected 50 stores, got {count}"

    def test_dim_sku_row_count(self):
        """dim_sku should have 1000 rows."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_dimensions.dim_sku").fetchone()[0]
        con.close()
        assert count == 1000, f"Expected 1000 SKUs, got {count}"

    def test_dim_vendor_row_count(self):
        """dim_vendor should have 5 rows."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_dimensions.dim_vendor").fetchone()[0]
        con.close()
        assert count == 5, f"Expected 5 vendors, got {count}"

    def test_dim_calendar_row_count(self):
        """dim_calendar should have 365 rows."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_dimensions.dim_calendar").fetchone()[0]
        con.close()
        assert count == 365, f"Expected 365 calendar days, got {count}"

    def test_mart_demand_base_has_data(self):
        """mart_demand_base should have substantial data."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_marts.mart_demand_base").fetchone()[0]
        con.close()
        assert count > 1000, f"Expected >1000 demand rows, got {count}"

    def test_mart_demand_base_has_all_signal_types(self):
        """mart_demand_base should contain all three demand signal types."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        result = con.execute("""
            select
                sum(sell_through_signal) as total_sell_through,
                sum(prescription_order_signal) as total_prescription,
                sum(display_interest_signal) as total_display_interest
            from main_marts.mart_demand_base
        """).fetchone()
        con.close()
        assert result[0] > 0, "No sell_through_signal found"
        assert result[1] > 0, "No prescription_order_signal found"
        assert result[2] > 0, "No display_interest_signal found"

    def test_mart_inventory_position_has_data(self):
        """mart_inventory_position should have data."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_marts.mart_inventory_position").fetchone()[0]
        con.close()
        assert count > 100, f"Expected >100 inventory positions, got {count}"

    def test_mart_inventory_position_valid_statuses(self):
        """All inventory statuses should be from the expected set."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        statuses = con.execute("select distinct inventory_status from main_marts.mart_inventory_position").fetchall()
        con.close()
        valid = {'stockout', 'stockout_pending_receipt', 'critical', 'low', 'healthy', 'excess', 'dead_stock'}
        actual = {s[0] for s in statuses}
        assert actual.issubset(valid), f"Invalid statuses: {actual - valid}"

    def test_mart_vendor_performance_has_all_vendors(self):
        """mart_vendor_performance should have all 5 vendors."""
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_marts.mart_vendor_performance").fetchone()[0]
        con.close()
        assert count == 5, f"Expected 5 vendors, got {count}"

    def test_data_validation_passes(self):
        """Run the validation script and check it passes."""
        result = run_cmd([sys.executable, "data/validate.py"])
        assert result.returncode == 0, f"Data validation failed:\n{result.stdout}\n{result.stderr}"
