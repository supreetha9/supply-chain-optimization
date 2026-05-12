"""Generate synthetic ERP-style supply chain dataset.

Produces 8 Parquet tables in data/raw/ plus CSV samples in data/sample/.

Causal chain (realism baked in so analytical results are believable):
  vendor.contract_lead_time_days  -> distribution of PO actual_arrival_date variance
  sku.seasonality_flag            -> demand exhibits weekly + monthly cycles + holiday spikes
  warehouse.capacity_units        -> upper bound on inventory snapshots
  demand spikes (Q-end, Black Fri) -> stockouts -> partial order fulfillment -> OTIF misses
  longer lead_time + variance     -> higher safety stock requirement (captured downstream)
  vendor.defect_rate              -> shipment defects feed vendor scorecard

Eight tables (ERP / SAP / NetSuite-inspired schema):
  dim_skus                  -- one row per SKU (~500)
  dim_vendors               -- one row per vendor (~20)
  dim_warehouses            -- one row per warehouse (5)
  fact_demand_daily         -- daily demand units per SKU x warehouse (sparse)
  fact_orders               -- customer orders with partial fulfillment
  fact_inventory_snapshot   -- weekly on-hand + reserved + in-transit
  fact_purchase_orders      -- POs with expected vs actual arrival dates
  fact_shipments            -- customer shipments with promised/shipped/delivered dates

Run:
    python -m python.src.generate_data
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "data" / "sample"

SEED = 11
NUM_SKUS = 500
NUM_VENDORS = 20
NUM_WAREHOUSES = 5
NUM_ORDERS = 30_000
NUM_PURCHASE_ORDERS = 4_000

START_DATE = pd.Timestamp("2024-01-01")
END_DATE = pd.Timestamp("2025-12-31")
DAYS = (END_DATE - START_DATE).days + 1

rng = np.random.default_rng(SEED)

# -----------------------------------------------------------------------------
# Domain constants
# -----------------------------------------------------------------------------

CATEGORIES = [
    ("electronics", ["phones", "tablets", "laptops", "accessories"]),
    ("apparel", ["mens", "womens", "kids", "footwear"]),
    ("home_goods", ["kitchen", "bedding", "decor", "tools"]),
    ("grocery", ["dry", "frozen", "beverage", "snacks"]),
    ("toys", ["plush", "outdoor", "educational", "games"]),
]

ABC_CLASSES = ["A", "B", "C"]
ABC_WEIGHTS = [0.20, 0.30, 0.50]

VENDOR_COUNTRIES = ["China", "USA", "Vietnam", "Mexico", "India"]
COUNTRY_LEAD_TIME_BASE = {"China": 35, "USA": 8, "Vietnam": 30, "Mexico": 12, "India": 28}

REGIONS = ["West", "Central", "East", "South", "International"]

CUSTOMER_SEGMENTS = ["enterprise", "smb", "consumer"]

# Holidays / spike days during the simulation window
HOLIDAY_SPIKES = {
    pd.Timestamp("2024-11-29"): 2.5,
    pd.Timestamp("2024-12-26"): 0.4,
    pd.Timestamp("2025-11-28"): 2.5,
    pd.Timestamp("2025-12-26"): 0.4,
    pd.Timestamp("2024-03-31"): 1.5,
    pd.Timestamp("2024-06-30"): 1.5,
    pd.Timestamp("2024-09-30"): 1.5,
    pd.Timestamp("2025-03-31"): 1.5,
    pd.Timestamp("2025-06-30"): 1.5,
    pd.Timestamp("2025-09-30"): 1.5,
}


# -----------------------------------------------------------------------------
# Dimension tables
# -----------------------------------------------------------------------------


def _generate_vendors() -> pd.DataFrame:
    countries = rng.choice(VENDOR_COUNTRIES, NUM_VENDORS, p=[0.35, 0.20, 0.20, 0.15, 0.10])
    contract_lead_time = np.array([COUNTRY_LEAD_TIME_BASE[c] for c in countries], dtype=float)
    contract_lead_time += rng.normal(0, 3, NUM_VENDORS)
    contract_lead_time = np.clip(contract_lead_time, 5, 45).round().astype(int)

    # Lead-time variance scales with the base (longer routes are more variable)
    lead_time_variance = (contract_lead_time * rng.uniform(0.10, 0.30, NUM_VENDORS)).round(2)

    payment_terms = rng.choice([15, 30, 45, 60, 90], NUM_VENDORS, p=[0.10, 0.40, 0.25, 0.20, 0.05])
    defect_rate = np.clip(rng.beta(2, 60, NUM_VENDORS), 0.001, 0.10).round(4)
    contract_start = pd.to_datetime(START_DATE) - pd.to_timedelta(
        rng.integers(180, 1800, NUM_VENDORS), unit="D"
    )

    return pd.DataFrame(
        {
            "vendor_id": [f"v_{i:03d}" for i in range(NUM_VENDORS)],
            "vendor_name": [f"Vendor {i:03d}" for i in range(NUM_VENDORS)],
            "country": countries,
            "contract_lead_time_days": contract_lead_time,
            "lead_time_variance_days": lead_time_variance,
            "payment_terms_days": payment_terms,
            "defect_rate": defect_rate,
            "contract_start_date": contract_start,
        }
    )


def _generate_skus(vendors: pd.DataFrame) -> pd.DataFrame:
    cat_choices = rng.choice(len(CATEGORIES), NUM_SKUS, p=[0.20, 0.20, 0.20, 0.25, 0.15])

    categories: list[str] = []
    subcategories: list[str] = []
    for idx in cat_choices:
        cat, subs = CATEGORIES[int(idx)]
        categories.append(cat)
        subcategories.append(str(rng.choice(subs)))

    unit_cost = np.round(rng.lognormal(mean=2.5, sigma=0.8, size=NUM_SKUS), 2)
    unit_cost = np.clip(unit_cost, 0.50, 1500.0)
    margin = rng.uniform(0.20, 0.80, NUM_SKUS)
    selling_price = np.round(unit_cost * (1 + margin), 2)

    storage_cost = np.round(unit_cost * rng.uniform(0.001, 0.005, NUM_SKUS), 4)
    shelf_life = rng.choice(
        [30, 90, 180, 365, 730, 1825], NUM_SKUS, p=[0.05, 0.10, 0.10, 0.20, 0.30, 0.25]
    )

    # Grocery + apparel are most seasonal
    seasonality_flag = np.array(
        [c in {"grocery", "apparel", "toys"} and rng.random() < 0.7 for c in categories],
        dtype=bool,
    )

    abc_class = rng.choice(ABC_CLASSES, NUM_SKUS, p=ABC_WEIGHTS)

    primary_vendor = rng.choice(vendors["vendor_id"].to_numpy(), NUM_SKUS)

    return pd.DataFrame(
        {
            "sku_id": [f"s_{i:05d}" for i in range(NUM_SKUS)],
            "sku_name": [f"SKU {i:05d}" for i in range(NUM_SKUS)],
            "category": categories,
            "subcategory": subcategories,
            "unit_cost": unit_cost,
            "selling_price": selling_price,
            "storage_cost_per_unit_per_day": storage_cost,
            "shelf_life_days": shelf_life,
            "seasonality_flag": seasonality_flag,
            "abc_class": abc_class,
            "primary_vendor_id": primary_vendor,
        }
    )


def _generate_warehouses() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "warehouse_id": [f"w_{i:02d}" for i in range(NUM_WAREHOUSES)],
            "warehouse_name": [f"{REGIONS[i]} DC" for i in range(NUM_WAREHOUSES)],
            "region": REGIONS,
            "capacity_units": rng.integers(80_000, 250_000, NUM_WAREHOUSES),
            "location_lat": rng.uniform(25.0, 49.0, NUM_WAREHOUSES).round(4),
            "location_lon": rng.uniform(-125.0, -68.0, NUM_WAREHOUSES).round(4),
        }
    )


# -----------------------------------------------------------------------------
# Demand fact (sparse: each SKU stocked at 2-3 warehouses on average)
# -----------------------------------------------------------------------------


def _stocking_pairs(skus: pd.DataFrame, warehouses: pd.DataFrame) -> pd.DataFrame:
    """Decide which (SKU, warehouse) pairs are actively stocked."""
    sku_ids = skus["sku_id"].to_numpy()
    wh_ids = warehouses["warehouse_id"].to_numpy()

    pairs = []
    for sku in sku_ids:
        # A class SKUs stocked everywhere; B at 3 warehouses; C at 2.
        abc = skus.loc[skus["sku_id"] == sku, "abc_class"].iloc[0]
        n_wh = {"A": 5, "B": 3, "C": 2}[abc]
        chosen = rng.choice(wh_ids, n_wh, replace=False)
        for w in chosen:
            pairs.append((sku, w))
    return pd.DataFrame(pairs, columns=["sku_id", "warehouse_id"])


def _generate_demand(
    skus: pd.DataFrame,
    pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Daily demand per (SKU, warehouse) with weekly/monthly seasonality + holidays."""
    dates = pd.date_range(START_DATE, END_DATE, freq="D")

    # Per-SKU base demand (lognormal around an ABC-tier mean)
    abc_to_base = {"A": 25.0, "B": 8.0, "C": 2.5}
    base_per_sku = {
        sku: max(0.5, float(rng.lognormal(mean=np.log(abc_to_base[abc]), sigma=0.6)))
        for sku, abc in zip(skus["sku_id"], skus["abc_class"], strict=False)
    }
    seasonal_per_sku = dict(zip(skus["sku_id"], skus["seasonality_flag"], strict=False))

    # Pre-compute date features
    dow = dates.dayofweek.to_numpy()
    month = dates.month.to_numpy()

    # Weekly multiplier: stronger weekend lift if seasonal flag
    weekly_seasonal = 1 + 0.30 * np.sin(2 * np.pi * dow / 7 + np.pi / 2)
    weekly_flat = np.ones_like(weekly_seasonal)
    # Monthly multiplier: peak around Nov-Dec for seasonal SKUs
    monthly_seasonal = 1 + 0.40 * np.sin(2 * np.pi * (month - 3) / 12)
    monthly_flat = np.ones_like(monthly_seasonal)

    holiday_mult = np.ones(len(dates))
    for h_date, mult in HOLIDAY_SPIKES.items():
        idx = (dates == h_date).nonzero()[0]
        if len(idx) > 0:
            holiday_mult[idx[0]] = mult

    rows: list[pd.DataFrame] = []
    for sku in pairs["sku_id"].unique():
        sku_pairs = pairs[pairs["sku_id"] == sku]["warehouse_id"].to_numpy()
        base = base_per_sku[sku]
        weekly = weekly_seasonal if seasonal_per_sku[sku] else weekly_flat
        monthly = monthly_seasonal if seasonal_per_sku[sku] else monthly_flat
        for wh in sku_pairs:
            wh_factor = float(rng.uniform(0.6, 1.4))
            mean = base * wh_factor * weekly * monthly * holiday_mult
            noise = rng.normal(1.0, 0.20, len(dates))
            units = np.clip(mean * noise, 0, None)
            rows.append(
                pd.DataFrame(
                    {
                        "demand_date": dates,
                        "sku_id": sku,
                        "warehouse_id": wh,
                        "units_demanded": units.round().astype(int),
                    }
                )
            )

    return pd.concat(rows, ignore_index=True)


# -----------------------------------------------------------------------------
# Orders + Shipments
# -----------------------------------------------------------------------------


def _generate_orders_and_shipments(
    pairs: pd.DataFrame,
    skus: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pair_arr = pairs.to_numpy()
    pair_idx = rng.integers(0, len(pair_arr), NUM_ORDERS)
    sku_ids = pair_arr[pair_idx, 0]
    wh_ids = pair_arr[pair_idx, 1]

    order_dates = pd.to_datetime(START_DATE) + pd.to_timedelta(
        rng.integers(0, DAYS, NUM_ORDERS), unit="D"
    )
    order_dates = order_dates + pd.to_timedelta(rng.integers(0, 86400, NUM_ORDERS), unit="s")

    units_ordered = rng.integers(1, 50, NUM_ORDERS)

    # Most orders are fully fulfilled; ~15% land in a partial-fulfillment regime,
    # and that rate roughly doubles on holiday spike days (drives OTIF misses).
    holiday_mask = np.asarray(order_dates.normalize().isin(list(HOLIDAY_SPIKES.keys())))
    base_partial_prob = 0.15
    partial_prob = np.where(holiday_mask, base_partial_prob * 2, base_partial_prob)
    is_partial = rng.random(NUM_ORDERS) < partial_prob
    fulfillment = np.where(is_partial, rng.uniform(0.40, 0.90, NUM_ORDERS), 1.0)
    units_fulfilled = (units_ordered * fulfillment).round().astype(int)
    units_fulfilled = np.minimum(units_fulfilled, units_ordered)
    # Floor: at least 1 unit if not totally stocked-out (5% of partials)
    totally_out = is_partial & (rng.random(NUM_ORDERS) < 0.05)
    units_fulfilled = np.where(totally_out, 0, units_fulfilled)

    customer_segment = rng.choice(CUSTOMER_SEGMENTS, NUM_ORDERS, p=[0.20, 0.35, 0.45])

    orders = pd.DataFrame(
        {
            "order_id": [f"o_{i:07d}" for i in range(NUM_ORDERS)],
            "order_date": order_dates,
            "sku_id": sku_ids,
            "warehouse_id": wh_ids,
            "customer_segment": customer_segment,
            "units_ordered": units_ordered,
            "units_fulfilled": units_fulfilled,
        }
    )

    # Shipment row exists only if units_fulfilled > 0
    shipped_mask = orders["units_fulfilled"] > 0
    shipped_orders = orders[shipped_mask].reset_index(drop=True)
    n_ship = len(shipped_orders)

    promised_offset = rng.choice([1, 2, 3, 5, 7], n_ship, p=[0.15, 0.30, 0.30, 0.20, 0.05])
    promised_date = (
        shipped_orders["order_date"] + pd.to_timedelta(promised_offset, unit="D")
    ).dt.normalize()

    # Most ship same-day or next-day; slip on holidays
    ship_offset = rng.choice([0, 1, 2], n_ship, p=[0.55, 0.35, 0.10])
    holiday_ship = (
        shipped_orders["order_date"].dt.normalize().isin(list(HOLIDAY_SPIKES.keys())).to_numpy()
    )
    ship_offset = np.where(holiday_ship, ship_offset + rng.integers(0, 3, n_ship), ship_offset)
    shipped_date = (
        shipped_orders["order_date"] + pd.to_timedelta(ship_offset, unit="D")
    ).dt.normalize()

    # Delivery: 1-4 days after ship; ~15% delivered late vs promised
    delivery_offset = rng.choice([1, 2, 3, 4], n_ship, p=[0.20, 0.40, 0.30, 0.10])
    delivered_date = shipped_date + pd.to_timedelta(delivery_offset, unit="D")

    shipments = pd.DataFrame(
        {
            "shipment_id": [f"sh_{i:07d}" for i in range(n_ship)],
            "order_id": shipped_orders["order_id"].to_numpy(),
            "sku_id": shipped_orders["sku_id"].to_numpy(),
            "warehouse_id": shipped_orders["warehouse_id"].to_numpy(),
            "promised_date": promised_date.to_numpy(),
            "shipped_date": shipped_date.to_numpy(),
            "delivered_date": delivered_date.to_numpy(),
            "units_shipped": shipped_orders["units_fulfilled"].to_numpy(),
        }
    )
    return orders, shipments


# -----------------------------------------------------------------------------
# Purchase orders (with vendor lead-time variance baked in)
# -----------------------------------------------------------------------------


def _generate_purchase_orders(
    skus: pd.DataFrame,
    vendors: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> pd.DataFrame:
    sku_arr = skus[["sku_id", "primary_vendor_id", "unit_cost"]].to_numpy()
    sku_idx = rng.integers(0, len(sku_arr), NUM_PURCHASE_ORDERS)
    sku_ids = sku_arr[sku_idx, 0]
    vendor_ids = sku_arr[sku_idx, 1]
    unit_costs_at_po = sku_arr[sku_idx, 2].astype(float) * rng.uniform(
        0.95, 1.05, NUM_PURCHASE_ORDERS
    )

    wh_ids = rng.choice(warehouses["warehouse_id"].to_numpy(), NUM_PURCHASE_ORDERS)

    po_dates = pd.to_datetime(START_DATE) + pd.to_timedelta(
        rng.integers(0, DAYS, NUM_PURCHASE_ORDERS), unit="D"
    )

    units_ordered = rng.integers(100, 5000, NUM_PURCHASE_ORDERS)

    # Map vendor -> contract_lead_time + variance
    vendor_lookup = vendors.set_index("vendor_id")[
        ["contract_lead_time_days", "lead_time_variance_days"]
    ].to_dict("index")
    contract_lt = np.array([vendor_lookup[v]["contract_lead_time_days"] for v in vendor_ids])
    lt_var = np.array([vendor_lookup[v]["lead_time_variance_days"] for v in vendor_ids])

    expected_arrival = po_dates + pd.to_timedelta(contract_lt.astype(int), unit="D")

    # Actual arrival = expected + N(0, variance) clipped to [-2, +14]
    actual_offset = rng.normal(0, lt_var, NUM_PURCHASE_ORDERS).clip(-2, 14).round().astype(int)
    actual_arrival = expected_arrival + pd.to_timedelta(actual_offset, unit="D")

    return pd.DataFrame(
        {
            "po_id": [f"po_{i:06d}" for i in range(NUM_PURCHASE_ORDERS)],
            "po_date": po_dates,
            "vendor_id": vendor_ids,
            "sku_id": sku_ids,
            "warehouse_id": wh_ids,
            "units_ordered": units_ordered,
            "expected_arrival_date": expected_arrival,
            "actual_arrival_date": actual_arrival,
            "unit_cost_at_po": np.round(unit_costs_at_po, 2),
        }
    )


# -----------------------------------------------------------------------------
# Inventory snapshots (weekly to keep size manageable)
# -----------------------------------------------------------------------------


def _generate_inventory_snapshots(
    pairs: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> pd.DataFrame:
    snapshot_dates = pd.date_range(START_DATE, END_DATE, freq="W-MON")

    capacity_lookup = warehouses.set_index("warehouse_id")["capacity_units"].to_dict()

    rows: list[pd.DataFrame] = []
    for _, pair in pairs.iterrows():
        sku = pair["sku_id"]
        wh = pair["warehouse_id"]
        capacity_share = float(capacity_lookup[wh]) / max(
            1, len(pairs[pairs["warehouse_id"] == wh])
        )
        # Random walk around 0.6 * capacity_share
        n = len(snapshot_dates)
        on_hand = (
            (
                np.clip(
                    0.6 * capacity_share + np.cumsum(rng.normal(0, capacity_share * 0.05, n)),
                    0,
                    capacity_share * 1.5,
                )
            )
            .round()
            .astype(int)
        )
        reserved = (on_hand * rng.uniform(0.05, 0.20, n)).round().astype(int)
        in_transit = (on_hand * rng.uniform(0.0, 0.15, n)).round().astype(int)

        rows.append(
            pd.DataFrame(
                {
                    "snapshot_date": snapshot_dates,
                    "sku_id": sku,
                    "warehouse_id": wh,
                    "on_hand_units": on_hand,
                    "reserved_units": reserved,
                    "in_transit_units": in_transit,
                }
            )
        )

    return pd.concat(rows, ignore_index=True)


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating dimensions...")
    vendors = _generate_vendors()
    skus = _generate_skus(vendors)
    warehouses = _generate_warehouses()

    print(f"  dim_vendors:    {len(vendors):,} rows")
    print(f"  dim_skus:       {len(skus):,} rows")
    print(f"  dim_warehouses: {len(warehouses):,} rows")

    pairs = _stocking_pairs(skus, warehouses)
    print(f"  stocking pairs: {len(pairs):,}")

    print("Generating fact_demand_daily...")
    demand = _generate_demand(skus, pairs)
    print(f"  fact_demand_daily: {len(demand):,} rows")

    print("Generating fact_orders + fact_shipments...")
    orders, shipments = _generate_orders_and_shipments(pairs, skus, warehouses)
    print(f"  fact_orders:    {len(orders):,} rows")
    print(f"  fact_shipments: {len(shipments):,} rows")

    print("Generating fact_purchase_orders...")
    purchase_orders = _generate_purchase_orders(skus, vendors, warehouses)
    print(f"  fact_purchase_orders: {len(purchase_orders):,} rows")

    print("Generating fact_inventory_snapshot...")
    inventory = _generate_inventory_snapshots(pairs, warehouses)
    print(f"  fact_inventory_snapshot: {len(inventory):,} rows")

    tables = {
        "dim_skus": skus,
        "dim_vendors": vendors,
        "dim_warehouses": warehouses,
        "fact_demand_daily": demand,
        "fact_orders": orders,
        "fact_inventory_snapshot": inventory,
        "fact_purchase_orders": purchase_orders,
        "fact_shipments": shipments,
    }

    print("Writing parquet + csv samples...")
    for name, df in tables.items():
        out_pq = RAW_DIR / f"{name}.parquet"
        df.to_parquet(out_pq, index=False)
        df.head(1000).to_csv(SAMPLE_DIR / f"{name}.csv", index=False)
        print(f"  {out_pq.relative_to(ROOT)}  ({len(df):,} rows)")

    print("Done.")


if __name__ == "__main__":
    main()
