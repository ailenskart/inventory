"""Shared test fixtures for the Lenskart Retail Intelligence Platform."""

import os
import sys

import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, "data", "dev.duckdb")
DBT_DIR = os.path.join(PROJECT_ROOT, "transform", "dbt")


@pytest.fixture(scope="session")
def project_root():
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def db_path():
    return DB_PATH


@pytest.fixture(scope="session")
def dbt_dir():
    return DBT_DIR


@pytest.fixture(scope="session")
def duckdb_connection():
    """Provide a read-only DuckDB connection for tests that need it."""
    if not os.path.exists(DB_PATH):
        pytest.skip("DuckDB not found — run 'make dbt-full' first")

    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    yield con
    con.close()
