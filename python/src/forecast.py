"""Prophet forecasting layer with MLflow run tracking.

Forecasts SKU x warehouse demand for the next ``horizon_days`` and persists
the result to ``data/forecast/fact_demand_forecast.parquet`` so dbt's
``stg_demand_forecast`` -> ``mart_forecast_accuracy`` chain can compare
forecast vs actual.

Each per-series Prophet fit logs to MLflow under experiment
``supply_chain_demand_forecast``:

  Params:    seasonality_mode, changepoint_prior_scale
  Metrics:   MAPE, WAPE, mean_bias, observation_count (holdout window)
  Tags:      sku_id, warehouse_id, abc_class, airflow_run_id (if env-injected)

Tracking URI is read from ``MLFLOW_TRACKING_URI`` at startup and the script
fails fast if it's unset (no silent file-store fallback).

Run:

    export MLFLOW_TRACKING_URI=http://localhost:5000   # or http://mlflow:5000 in docker
    python -m python.src.forecast --top-n 50

To forecast every (SKU, warehouse) pair, omit ``--top-n``.
"""

from __future__ import annotations

import argparse
import logging
import os
import uuid
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from prophet import Prophet  # noqa: F401  (only for typing)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
FORECAST_DIR = ROOT / "data" / "forecast"
FORECAST_PATH = FORECAST_DIR / "fact_demand_forecast.parquet"

EXPERIMENT_NAME = "supply_chain_demand_forecast"
HOLDOUT_DAYS = 30
DEFAULT_HORIZON_DAYS = 30

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Tracking-URI guard (fail fast)
# -----------------------------------------------------------------------------


def require_tracking_uri() -> str:
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        raise RuntimeError(
            "MLFLOW_TRACKING_URI is not set. Export it before running forecast.py:\n"
            "  export MLFLOW_TRACKING_URI=http://localhost:5000   # local docker\n"
            "  export MLFLOW_TRACKING_URI=http://mlflow:5000      # inside compose network\n"
            "(forecast.py refuses to silently fall back to a local file store.)"
        )
    return uri


# -----------------------------------------------------------------------------
# Per-series fit
# -----------------------------------------------------------------------------


def _silence_prophet() -> None:
    """Prophet is famously chatty; lower its logger to WARN."""
    for name in ("prophet", "cmdstanpy"):
        logging.getLogger(name).setLevel(logging.WARNING)


def fit_prophet(
    history: pd.DataFrame,
    *,
    is_seasonal: bool,
    horizon_days: int,
    holdout_days: int,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, str | float]]:
    """Fit Prophet on a single (SKU, warehouse) history.

    Args:
        history: DataFrame with columns ``ds`` (date) and ``y`` (units demanded).
        is_seasonal: Whether to enable yearly seasonality (cheaper to skip for
            non-seasonal SKUs).
        horizon_days: Number of future days to forecast.
        holdout_days: Number of trailing days held out for in-sample MAPE/WAPE.

    Returns:
        Tuple of (forecast_df, metrics, params). forecast_df has columns
        ``ds, yhat, yhat_lower, yhat_upper`` over the future horizon.
    """
    from prophet import Prophet

    _silence_prophet()

    if len(history) < holdout_days + 30:
        msg = f"history too short ({len(history)} rows) for holdout={holdout_days}"
        raise ValueError(msg)

    train = history.iloc[:-holdout_days]
    holdout = history.iloc[-holdout_days:]

    params = {
        "seasonality_mode": "multiplicative" if is_seasonal else "additive",
        "changepoint_prior_scale": 0.05,
        "weekly_seasonality": True,
        "yearly_seasonality": is_seasonal,
        "daily_seasonality": False,
    }

    model = Prophet(**params)
    with suppress(Exception):
        # US-flavored holidays nudge the spike days the generator bakes in.
        model.add_country_holidays(country_name="US")
    model.fit(train)

    horizon_total = holdout_days + horizon_days
    future = model.make_future_dataframe(periods=horizon_total, freq="D", include_history=False)
    forecast = model.predict(future)

    # Holdout metrics
    holdout_pred = forecast.head(holdout_days)["yhat"].to_numpy()
    holdout_actual = holdout["y"].to_numpy()
    abs_err = np.abs(holdout_pred - holdout_actual)
    actual_sum = holdout_actual.sum()
    metrics = {
        "mape": float(
            np.mean(
                np.where(holdout_actual > 0, abs_err / np.maximum(holdout_actual, 1e-9), np.nan)
            )
        ),
        "wape": float(abs_err.sum() / actual_sum) if actual_sum > 0 else float("nan"),
        "mean_bias": float((holdout_pred - holdout_actual).mean()),
        "observation_count": float(len(holdout_actual)),
    }

    # Forward-looking horizon (drop the holdout slice)
    horizon = forecast.tail(horizon_days)[["ds", "yhat", "yhat_lower", "yhat_upper"]].reset_index(
        drop=True
    )
    return (
        horizon,
        metrics,
        {k: v for k, v in params.items() if isinstance(v, str | int | float | bool)},
    )


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------


def _load_history() -> tuple[pd.DataFrame, pd.DataFrame]:
    demand = pd.read_parquet(RAW_DIR / "fact_demand_daily.parquet")
    demand["demand_date"] = pd.to_datetime(demand["demand_date"])
    skus = pd.read_parquet(RAW_DIR / "dim_skus.parquet")[
        ["sku_id", "abc_class", "seasonality_flag"]
    ]
    return demand, skus


def _select_series(demand: pd.DataFrame, top_n: int | None) -> list[tuple[str, str]]:
    """Choose which (SKU, warehouse) pairs to forecast.

    If ``top_n`` is set, we forecast only the top-N pairs by 90-day demand
    volume. This keeps the dashboard workflow fast (~50 fits, ~3 minutes)
    while still demonstrating the architecture. To run the full ~1500 pairs,
    pass ``top_n=None``.
    """
    cutoff = demand["demand_date"].max() - pd.Timedelta(days=90)
    recent = demand[demand["demand_date"] >= cutoff]
    ranked = (
        recent.groupby(["sku_id", "warehouse_id"])["units_demanded"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    if top_n is not None:
        ranked = ranked.head(top_n)
    return [(row.sku_id, row.warehouse_id) for row in ranked.itertuples(index=False)]


def forecast_all(
    *,
    top_n: int | None = 50,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    holdout_days: int = HOLDOUT_DAYS,
) -> pd.DataFrame:
    """Forecast every selected (SKU, warehouse) pair, log to MLflow, return long DF."""
    import mlflow

    mlflow.set_tracking_uri(require_tracking_uri())
    mlflow.set_experiment(EXPERIMENT_NAME)

    demand, skus = _load_history()
    seasonality_lookup = dict(zip(skus["sku_id"], skus["seasonality_flag"], strict=False))
    abc_lookup = dict(zip(skus["sku_id"], skus["abc_class"], strict=False))

    pairs = _select_series(demand, top_n)
    logger.info("Forecasting %d (SKU, warehouse) pairs", len(pairs))

    model_run_id = uuid.uuid4().hex[:12]
    airflow_run_id = os.environ.get("AIRFLOW_CTX_DAG_RUN_ID", "")

    out_rows: list[pd.DataFrame] = []
    n_skipped = 0

    with mlflow.start_run(run_name=f"batch_{model_run_id}") as parent_run:
        mlflow.log_param("series_count", len(pairs))
        mlflow.log_param("horizon_days", horizon_days)
        mlflow.log_param("holdout_days", holdout_days)
        mlflow.log_param("top_n", top_n if top_n is not None else "all")
        mlflow.set_tag("model_run_id", model_run_id)
        if airflow_run_id:
            mlflow.set_tag("airflow_run_id", airflow_run_id)

        for sku_id, warehouse_id in pairs:
            history = (
                demand[(demand["sku_id"] == sku_id) & (demand["warehouse_id"] == warehouse_id)]
                .sort_values("demand_date")
                .rename(columns={"demand_date": "ds", "units_demanded": "y"})[["ds", "y"]]
                .reset_index(drop=True)
            )

            try:
                horizon, metrics, params = fit_prophet(
                    history,
                    is_seasonal=bool(seasonality_lookup.get(sku_id, False)),
                    horizon_days=horizon_days,
                    holdout_days=holdout_days,
                )
            except Exception as exc:
                logger.warning("Skipping %s/%s: %s", sku_id, warehouse_id, exc)
                n_skipped += 1
                continue

            with mlflow.start_run(
                run_name=f"{sku_id}_{warehouse_id}",
                nested=True,
                parent_run_id=parent_run.info.run_id,
            ):
                mlflow.set_tag("sku_id", sku_id)
                mlflow.set_tag("warehouse_id", warehouse_id)
                mlflow.set_tag("abc_class", abc_lookup.get(sku_id, "?"))
                mlflow.set_tag("model_run_id", model_run_id)
                if airflow_run_id:
                    mlflow.set_tag("airflow_run_id", airflow_run_id)

                for k, v in params.items():
                    mlflow.log_param(k, v)
                for k, v in metrics.items():
                    if v is not None and not (isinstance(v, float) and np.isnan(v)):
                        mlflow.log_metric(k, float(v))

            horizon = horizon.assign(
                sku_id=sku_id,
                warehouse_id=warehouse_id,
                model_run_id=model_run_id,
            ).rename(columns={"ds": "forecast_date"})
            out_rows.append(horizon)

        mlflow.log_metric("skipped_series", float(n_skipped))

    if not out_rows:
        msg = "No series produced a forecast; check input data and history length."
        raise RuntimeError(msg)

    forecast = pd.concat(out_rows, ignore_index=True)
    forecast = forecast[
        [
            "forecast_date",
            "sku_id",
            "warehouse_id",
            "yhat",
            "yhat_lower",
            "yhat_upper",
            "model_run_id",
        ]
    ]
    forecast["forecast_date"] = pd.to_datetime(forecast["forecast_date"]).dt.normalize()
    return forecast


def persist_forecast(forecast: pd.DataFrame) -> Path:
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    forecast.to_parquet(FORECAST_PATH, index=False)
    return FORECAST_PATH


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prophet + MLflow demand forecasting.")
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Forecast only the top-N (SKU, warehouse) pairs by 90-day demand. "
        "Pass --all for every pair.",
    )
    parser.add_argument("--all", action="store_true", help="Forecast every pair.")
    parser.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    parser.add_argument("--holdout-days", type=int, default=HOLDOUT_DAYS)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _build_parser().parse_args()
    top_n = None if args.all else args.top_n

    forecast = forecast_all(
        top_n=top_n,
        horizon_days=args.horizon_days,
        holdout_days=args.holdout_days,
    )
    out_path = persist_forecast(forecast)
    logger.info("Wrote %d forecast rows -> %s", len(forecast), out_path)


if __name__ == "__main__":
    main()
