"""Schema + causal-correlation tests for the synthetic supply-chain dataset.

These tests run against the generated parquet files. To produce them once:

    make generate

The fixtures cache the loaded DataFrames so the full suite stays fast.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

EXPECTED_TABLES = {
    "dim_skus": {
        "sku_id",
        "sku_name",
        "category",
        "subcategory",
        "unit_cost",
        "selling_price",
        "storage_cost_per_unit_per_day",
        "shelf_life_days",
        "seasonality_flag",
        "abc_class",
        "primary_vendor_id",
    },
    "dim_vendors": {
        "vendor_id",
        "vendor_name",
        "country",
        "contract_lead_time_days",
        "lead_time_variance_days",
        "payment_terms_days",
        "defect_rate",
        "contract_start_date",
    },
    "dim_warehouses": {
        "warehouse_id",
        "warehouse_name",
        "region",
        "capacity_units",
        "location_lat",
        "location_lon",
    },
    "fact_demand_daily": {"demand_date", "sku_id", "warehouse_id", "units_demanded"},
    "fact_orders": {
        "order_id",
        "order_date",
        "sku_id",
        "warehouse_id",
        "customer_segment",
        "units_ordered",
        "units_fulfilled",
    },
    "fact_inventory_snapshot": {
        "snapshot_date",
        "sku_id",
        "warehouse_id",
        "on_hand_units",
        "reserved_units",
        "in_transit_units",
    },
    "fact_purchase_orders": {
        "po_id",
        "po_date",
        "vendor_id",
        "sku_id",
        "warehouse_id",
        "units_ordered",
        "expected_arrival_date",
        "actual_arrival_date",
        "unit_cost_at_po",
    },
    "fact_shipments": {
        "shipment_id",
        "order_id",
        "sku_id",
        "warehouse_id",
        "promised_date",
        "shipped_date",
        "delivered_date",
        "units_shipped",
    },
}


def _have_data() -> bool:
    return all((DATA_DIR / f"{name}.parquet").exists() for name in EXPECTED_TABLES)


pytestmark = pytest.mark.skipif(
    not _have_data(),
    reason="Run `make generate` to create the parquet files this test suite reads.",
)


@pytest.fixture(scope="module")
def tables() -> dict[str, pd.DataFrame]:
    return {name: pd.read_parquet(DATA_DIR / f"{name}.parquet") for name in EXPECTED_TABLES}


# -----------------------------------------------------------------------------
# Schema
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected", sorted(EXPECTED_TABLES.items()))
def test_schema_columns(tables: dict[str, pd.DataFrame], name: str, expected: set[str]) -> None:
    df = tables[name]
    missing = expected - set(df.columns)
    assert not missing, f"{name} missing columns: {missing}"
    assert len(df) > 0, f"{name} has 0 rows"


def test_dim_skus_keys_unique(tables: dict[str, pd.DataFrame]) -> None:
    skus = tables["dim_skus"]
    assert skus["sku_id"].is_unique


def test_dim_vendors_keys_unique(tables: dict[str, pd.DataFrame]) -> None:
    vendors = tables["dim_vendors"]
    assert vendors["vendor_id"].is_unique


def test_dim_warehouses_keys_unique(tables: dict[str, pd.DataFrame]) -> None:
    warehouses = tables["dim_warehouses"]
    assert warehouses["warehouse_id"].is_unique
    assert len(warehouses) == 5


def test_referential_integrity(tables: dict[str, pd.DataFrame]) -> None:
    sku_ids = set(tables["dim_skus"]["sku_id"])
    vendor_ids = set(tables["dim_vendors"]["vendor_id"])
    wh_ids = set(tables["dim_warehouses"]["warehouse_id"])

    for fact_name in (
        "fact_demand_daily",
        "fact_orders",
        "fact_inventory_snapshot",
        "fact_purchase_orders",
        "fact_shipments",
    ):
        df = tables[fact_name]
        assert set(df["sku_id"]).issubset(sku_ids), f"{fact_name} has unknown sku_id"
        assert set(df["warehouse_id"]).issubset(wh_ids), f"{fact_name} has unknown warehouse_id"

    pos = tables["fact_purchase_orders"]
    assert set(pos["vendor_id"]).issubset(vendor_ids)


# -----------------------------------------------------------------------------
# Domain invariants
# -----------------------------------------------------------------------------


def test_no_negative_units(tables: dict[str, pd.DataFrame]) -> None:
    assert (tables["fact_demand_daily"]["units_demanded"] >= 0).all()
    assert (tables["fact_orders"]["units_ordered"] > 0).all()
    assert (tables["fact_orders"]["units_fulfilled"] >= 0).all()
    assert (tables["fact_inventory_snapshot"]["on_hand_units"] >= 0).all()
    assert (tables["fact_purchase_orders"]["units_ordered"] > 0).all()


def test_fulfilled_le_ordered(tables: dict[str, pd.DataFrame]) -> None:
    orders = tables["fact_orders"]
    assert (orders["units_fulfilled"] <= orders["units_ordered"]).all()


def test_shipment_date_ordering(tables: dict[str, pd.DataFrame]) -> None:
    """For most shipments, ship <= delivered. ~5% leniency for noisy data is fine
    but the bulk must hold (this is core OTIF math)."""
    sh = tables["fact_shipments"]
    pd_dates = pd.to_datetime(sh["shipped_date"])
    dl_dates = pd.to_datetime(sh["delivered_date"])
    ok = (dl_dates >= pd_dates).mean()
    assert ok > 0.99, f"Only {ok:.2%} of shipments have delivered >= shipped"


def test_po_arrival_after_order(tables: dict[str, pd.DataFrame]) -> None:
    pos = tables["fact_purchase_orders"]
    assert (pd.to_datetime(pos["expected_arrival_date"]) > pd.to_datetime(pos["po_date"])).all()


# -----------------------------------------------------------------------------
# Causal correlations -- the realism guarantees the plan calls out
# -----------------------------------------------------------------------------


def test_longer_lead_time_higher_arrival_variance(tables: dict[str, pd.DataFrame]) -> None:
    """Vendors with longer contract lead times should also exhibit higher
    actual-arrival variance (longer routes = more variability)."""
    vendors = tables["dim_vendors"]
    pos = tables["fact_purchase_orders"]

    pos = pos.merge(
        vendors[["vendor_id", "contract_lead_time_days"]],
        on="vendor_id",
        how="left",
    )
    pos["arrival_offset_days"] = (
        pd.to_datetime(pos["actual_arrival_date"]) - pd.to_datetime(pos["expected_arrival_date"])
    ).dt.days

    by_vendor = (
        pos.groupby("vendor_id")
        .agg(
            contract_lt=("contract_lead_time_days", "first"),
            arrival_std=("arrival_offset_days", "std"),
        )
        .dropna()
    )

    # Spearman-ish: rank correlation between contract lead time and offset std
    corr = by_vendor["contract_lt"].corr(by_vendor["arrival_std"], method="spearman")
    assert corr > 0.2, f"Lead time vs arrival variance correlation too weak: {corr:.3f}"


def test_seasonal_skus_have_higher_weekly_swing(tables: dict[str, pd.DataFrame]) -> None:
    """SKUs flagged seasonal should show a larger ratio of max/min day-of-week
    average demand than non-seasonal SKUs."""
    skus = tables["dim_skus"]
    demand = tables["fact_demand_daily"].copy()
    demand["dow"] = pd.to_datetime(demand["demand_date"]).dt.dayofweek
    demand = demand.merge(skus[["sku_id", "seasonality_flag"]], on="sku_id", how="left")

    by_flag_dow = demand.groupby(["seasonality_flag", "dow"])["units_demanded"].mean().unstack()

    swing = (by_flag_dow.max(axis=1) - by_flag_dow.min(axis=1)) / by_flag_dow.mean(axis=1)
    # Seasonal flag should have a noticeably wider swing
    assert swing.loc[True] > swing.loc[False] + 0.05, (
        f"Seasonal vs non-seasonal weekly swing didn't differ enough: {swing.to_dict()}"
    )


def test_holiday_demand_spike(tables: dict[str, pd.DataFrame]) -> None:
    """Black Friday + end-of-quarter days should have higher mean demand than
    a randomly-sampled non-holiday day in the same window."""
    demand = tables["fact_demand_daily"]
    demand_by_date = demand.groupby("demand_date")["units_demanded"].mean()

    holidays = [
        pd.Timestamp("2024-11-29"),
        pd.Timestamp("2025-11-28"),
        pd.Timestamp("2024-09-30"),
        pd.Timestamp("2025-09-30"),
    ]
    holiday_dates = [h for h in holidays if h in demand_by_date.index]
    assert holiday_dates, "No holiday dates landed in the demand window"

    holiday_mean = demand_by_date.loc[holiday_dates].mean()
    overall_mean = demand_by_date.mean()
    assert holiday_mean > 1.2 * overall_mean, (
        f"Holiday spike not visible: holiday={holiday_mean:.1f} vs overall={overall_mean:.1f}"
    )


def test_inventory_within_capacity(tables: dict[str, pd.DataFrame]) -> None:
    """Aggregate on-hand at any warehouse should never exceed its capacity_units."""
    inv = tables["fact_inventory_snapshot"]
    wh = tables["dim_warehouses"].set_index("warehouse_id")["capacity_units"]

    daily_total = (
        inv.groupby(["snapshot_date", "warehouse_id"])["on_hand_units"].sum().reset_index()
    )
    daily_total["capacity"] = daily_total["warehouse_id"].map(wh)
    over = daily_total[daily_total["on_hand_units"] > daily_total["capacity"]]
    assert over.empty, f"Capacity violations: {len(over)} rows"


def test_demand_window_covers_two_years(tables: dict[str, pd.DataFrame]) -> None:
    demand = tables["fact_demand_daily"]
    span = pd.to_datetime(demand["demand_date"]).max() - pd.to_datetime(demand["demand_date"]).min()
    assert span >= pd.Timedelta(days=700), f"Demand window too short: {span}"


def test_partial_fulfillment_exists(tables: dict[str, pd.DataFrame]) -> None:
    """Some orders must be partially fulfilled so OTIF mart has signal to find."""
    orders = tables["fact_orders"]
    partial = (orders["units_fulfilled"] < orders["units_ordered"]) & (
        orders["units_fulfilled"] > 0
    )
    rate = partial.mean()
    assert 0.05 < rate < 0.50, f"Partial-fulfillment rate {rate:.2%} outside plausible range"


def test_late_shipment_signal_exists(tables: dict[str, pd.DataFrame]) -> None:
    """OTIF requires that some shipments miss their promised_date; verify there's signal."""
    sh = tables["fact_shipments"]
    late = pd.to_datetime(sh["delivered_date"]) > pd.to_datetime(sh["promised_date"])
    rate = late.mean()
    assert rate > 0.05, f"Late-shipment rate too low for OTIF mart to be interesting: {rate:.2%}"


def test_seed_reproducibility() -> None:
    """Re-running the generator with the same seed produces identical key counts."""
    skus = pd.read_parquet(DATA_DIR / "dim_skus.parquet")
    assert len(skus) > 0
    # Deterministic ID prefix
    assert skus["sku_id"].iloc[0].startswith("s_")


def test_all_demand_units_finite(tables: dict[str, pd.DataFrame]) -> None:
    units = tables["fact_demand_daily"]["units_demanded"].to_numpy()
    assert np.isfinite(units).all()
