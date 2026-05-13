"""Cached data loaders for the supply-chain Streamlit dashboard.

Reads from:
  - dbt-built DuckDB warehouse at data/supply.duckdb
  - Forecast/optimizer parquet artifacts at data/forecast/
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = PROJECT_ROOT / "data" / "supply.duckdb"
FORECAST_DIR = PROJECT_ROOT / "data" / "forecast"
ALERTS_LOG = PROJECT_ROOT / "data" / "alerts.log"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

MLFLOW_UI_URL = os.environ.get("MLFLOW_UI_URL", "http://localhost:5000")
AIRFLOW_UI_URL = os.environ.get("AIRFLOW_UI_URL", "http://localhost:8080")


def _query(sql: str) -> pd.DataFrame:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


# ── Marts ────────────────────────────────────────────────────────────────────


@st.cache_data
def load_inventory_health() -> pd.DataFrame:
    return _query("select * from main_marts.mart_inventory_health")


@st.cache_data
def load_otif() -> pd.DataFrame:
    df = _query("select * from main_marts.mart_otif")
    df["ship_month"] = pd.to_datetime(df["ship_month"])
    return df


@st.cache_data
def load_vendor_scorecard() -> pd.DataFrame:
    return _query("select * from main_marts.mart_vendor_scorecard")


@st.cache_data
def load_warehouse_performance() -> pd.DataFrame:
    return _query("select * from main_marts.mart_warehouse_performance")


@st.cache_data
def load_forecast_accuracy() -> pd.DataFrame:
    return _query("select * from main_marts.mart_forecast_accuracy")


@st.cache_data
def load_reorder_recommendations() -> pd.DataFrame:
    return _query("select * from main_marts.mart_reorder_recommendations")


# ── Forecast / optimizer parquet ─────────────────────────────────────────────


@st.cache_data
def load_forecast_artifact() -> pd.DataFrame:
    path = FORECAST_DIR / "fact_demand_forecast.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df = df[df["sku_id"] != "__placeholder__"]
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])
    return df.reset_index(drop=True)


@st.cache_data
def load_reorder_optimized() -> pd.DataFrame:
    path = FORECAST_DIR / "reorder_recommendations.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data
def load_vendor_scores_artifact() -> pd.DataFrame:
    path = FORECAST_DIR / "vendor_scores.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


# ── Raw history (for forecast vs actual chart) ───────────────────────────────


@st.cache_data
def load_demand_history() -> pd.DataFrame:
    path = RAW_DIR / "fact_demand_daily.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["demand_date"] = pd.to_datetime(df["demand_date"])
    return df


# ── Run-status helpers ───────────────────────────────────────────────────────


@st.cache_data(ttl=60)
def latest_alerts(n: int = 5) -> list[str]:
    if not ALERTS_LOG.exists():
        return []
    with ALERTS_LOG.open("r", encoding="utf-8") as fh:
        return fh.readlines()[-n:]


def health_check() -> tuple[bool, str]:
    """Return (db_present, message). Used to show a friendly nudge if the user
    hasn't run the pipeline yet."""
    if not DUCKDB_PATH.exists():
        return False, (
            "data/supply.duckdb not found. Run `make pipeline` in your shell, "
            "or `make airflow-up && make airflow-trigger` to invoke the daily DAG."
        )
    return True, ""
