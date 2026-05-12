"""End-to-end smoke tests for the dbt pipeline.

These tests query the materialized DuckDB warehouse (data/supply.duckdb) and
verify that the dbt build produced the marts the rest of the project relies on.

Pre-requisites (run once before this test):

    make pipeline    # generate -> dbt build -> forecast -> dbt build-post

Or, for the dbt-only subset:

    make generate
    cd dbt_project && DBT_PROFILES_DIR=. dbt build
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = PROJECT_ROOT / "data" / "supply.duckdb"

EXPECTED_MARTS = [
    "mart_inventory_health",
    "mart_otif",
    "mart_vendor_scorecard",
    "mart_warehouse_performance",
    "mart_forecast_accuracy",
    "mart_reorder_recommendations",
]

EXPECTED_STAGING = [
    "stg_skus",
    "stg_vendors",
    "stg_warehouses",
    "stg_demand_daily",
    "stg_orders",
    "stg_inventory_snapshot",
    "stg_purchase_orders",
    "stg_shipments",
    "stg_demand_forecast",
]

EXPECTED_SNAPSHOTS = [
    "vendor_contract_snapshot",
    "sku_pricing_snapshot",
]


pytestmark = pytest.mark.skipif(
    not DUCKDB_PATH.exists(),
    reason="Run `make pipeline` (or `make generate && dbt build`) first to materialize data/supply.duckdb",
)


@pytest.fixture(scope="module")
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    yield c
    c.close()


def _list_tables(conn: duckdb.DuckDBPyConnection, schema: str) -> set[str]:
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = ?",
        [schema],
    ).fetchall()
    return {r[0] for r in rows}


@pytest.mark.parametrize("model", EXPECTED_STAGING)
def test_staging_exists(conn: duckdb.DuckDBPyConnection, model: str) -> None:
    tables = _list_tables(conn, "main_staging")
    assert model in tables, f"staging.{model} missing; got {sorted(tables)}"


@pytest.mark.parametrize("model", EXPECTED_MARTS)
def test_mart_exists_and_nonempty(conn: duckdb.DuckDBPyConnection, model: str) -> None:
    tables = _list_tables(conn, "main_marts")
    assert model in tables, f"marts.{model} missing; got {sorted(tables)}"
    if model in {"mart_forecast_accuracy", "mart_reorder_recommendations"}:
        # These depend on Prophet output; may legitimately be 0 rows on first run.
        return
    n = conn.execute(f"select count(*) from main_marts.{model}").fetchone()[0]
    assert n > 0, f"marts.{model} is empty"


@pytest.mark.parametrize("snap", EXPECTED_SNAPSHOTS)
def test_snapshot_exists(conn: duckdb.DuckDBPyConnection, snap: str) -> None:
    tables = _list_tables(conn, "snapshots")
    assert snap in tables


def test_inventory_health_columns(conn: duckdb.DuckDBPyConnection) -> None:
    cols = {
        r[0]
        for r in conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'main_marts' and table_name = 'mart_inventory_health'"
        ).fetchall()
    }
    expected = {
        "sku_id",
        "warehouse_id",
        "on_hand_units",
        "available_units",
        "days_of_supply_30d",
        "stockout_risk_score",
        "is_slow_moving",
        "on_hand_value_usd",
        "abc_class",
        "target_service_level",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


def test_otif_rate_in_range(conn: duckdb.DuckDBPyConnection) -> None:
    rows = conn.execute(
        "select min(otif_rate), max(otif_rate) from main_marts.mart_otif"
    ).fetchone()
    assert rows[0] >= 0.0
    assert rows[1] <= 1.0


def test_vendor_scorecard_score_bounded(conn: duckdb.DuckDBPyConnection) -> None:
    rows = conn.execute(
        "select min(composite_score), max(composite_score) from main_marts.mart_vendor_scorecard"
    ).fetchone()
    assert rows[0] >= 0.0
    assert rows[1] <= 100.0


def test_warehouse_performance_one_row_per_warehouse(conn: duckdb.DuckDBPyConnection) -> None:
    n_total, n_unique = conn.execute(
        "select count(*), count(distinct warehouse_id) from main_marts.mart_warehouse_performance"
    ).fetchone()
    assert n_total == n_unique
    assert n_total >= 5


def test_inventory_position_consistency(conn: duckdb.DuckDBPyConnection) -> None:
    """available_units = on_hand - reserved at the latest snapshot."""
    bad = conn.execute(
        "select count(*) from main_marts.mart_inventory_health "
        "where available_units != on_hand_units - reserved_units"
    ).fetchone()[0]
    assert bad == 0


def test_seeds_loaded(conn: duckdb.DuckDBPyConnection) -> None:
    assert "service_level_targets" in _list_tables(conn, "main_seeds")
    assert "stockout_cost_overrides" in _list_tables(conn, "main_seeds")


def test_stg_demand_forecast_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Schema must be in place even if forecast.py hasn't run yet."""
    cols = {
        r[0]
        for r in conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'main_staging' and table_name = 'stg_demand_forecast'"
        ).fetchall()
    }
    assert {
        "forecast_date",
        "sku_id",
        "warehouse_id",
        "forecast_units",
        "forecast_units_lower",
        "forecast_units_upper",
        "model_run_id",
    } == cols
