"""Top-level analysis orchestration: forecast -> optimize -> vendor score -> alerts.

For ad-hoc host-side runs (`make analyze`). The Airflow DAG calls each step
as a separate `BashOperator` task, but this module provides a single Python
entry point that's easier to debug.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from .forecast import forecast_all
from .forecast import persist_forecast as persist_forecast_artifact
from .optimization import load_optimization_inputs, optimize_all
from .vendor_scoring import _load_inputs as load_vendor_inputs
from .vendor_scoring import compute_scores

ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = ROOT / "data" / "supply.duckdb"
ALERTS_LOG = ROOT / "data" / "alerts.log"
FORECAST_DIR = ROOT / "data" / "forecast"

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Alerts
# -----------------------------------------------------------------------------


def detect_alerts(duckdb_path: Path = DUCKDB_PATH) -> pd.DataFrame:
    """Surface SKU/warehouse pairs that need immediate attention.

    Triggers:
      - inventory_position < safety_stock_baseline (textbook)  -> 'reorder_needed'
      - stockout_risk_score >= 0.85                            -> 'imminent_stockout'
      - days_of_supply_30d > 180 and is_slow_moving            -> 'excess_inventory'
    """
    sql = """
    with reco as (
        select sku_id, warehouse_id, sku_name, abc_class,
               inventory_position, reorder_point_baseline, needs_reorder
        from main_marts.mart_reorder_recommendations
    ),
    health as (
        select sku_id, warehouse_id, stockout_risk_score,
               days_of_supply_30d, is_slow_moving
        from main_marts.mart_inventory_health
    )
    select
        r.sku_id,
        r.warehouse_id,
        r.sku_name,
        r.abc_class,
        r.inventory_position,
        r.reorder_point_baseline,
        h.stockout_risk_score,
        h.days_of_supply_30d,
        h.is_slow_moving,
        case
            when h.stockout_risk_score >= 0.85 then 'imminent_stockout'
            when r.needs_reorder then 'reorder_needed'
            when h.days_of_supply_30d > 180 and h.is_slow_moving then 'excess_inventory'
            else null
        end as alert_type
    from reco r
    left join health h on h.sku_id = r.sku_id and h.warehouse_id = r.warehouse_id
    """
    with duckdb.connect(str(duckdb_path), read_only=True) as conn:
        df = conn.execute(sql).df()
    return df[df["alert_type"].notna()].reset_index(drop=True)


def _write_alerts_log(alerts: pd.DataFrame, log_path: Path = ALERTS_LOG) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    counts = alerts["alert_type"].value_counts().to_dict()
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] alerts: {summary} (total {len(alerts)})\n")


# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------


def run_pipeline(*, top_n: int | None = 50) -> None:
    logger.info("Step 1/4: Prophet forecast")
    forecast = forecast_all(top_n=top_n)
    persist_forecast_artifact(forecast)

    logger.info("Step 2/4: dbt re-build (forecast-dependent marts) -- run separately:")
    logger.info("    cd dbt_project && dbt build --select tag:needs_forecast+")

    logger.info("Step 3/4: OR-Tools reorder optimization")
    opt_df = load_optimization_inputs()
    opt_results = optimize_all(opt_df)
    opt_path = FORECAST_DIR / "reorder_recommendations.parquet"
    opt_path.parent.mkdir(parents=True, exist_ok=True)
    opt_results.to_parquet(opt_path, index=False)
    logger.info("Wrote %d reorder recommendations -> %s", len(opt_results), opt_path)

    logger.info("Step 3.5/4: Composite vendor scoring")
    vendor_df = load_vendor_inputs()
    vendor_scored = compute_scores(vendor_df)
    vendor_path = FORECAST_DIR / "vendor_scores.parquet"
    vendor_scored.to_parquet(vendor_path, index=False)
    logger.info("Wrote %d vendor scores -> %s", len(vendor_scored), vendor_path)

    logger.info("Step 4/4: Alerting")
    alerts = detect_alerts()
    _write_alerts_log(alerts)
    logger.info("Detected %d alerts -> %s", len(alerts), ALERTS_LOG)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="End-to-end supply-chain analysis pipeline.")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    run_pipeline(top_n=None if args.all else args.top_n)


if __name__ == "__main__":
    main()
