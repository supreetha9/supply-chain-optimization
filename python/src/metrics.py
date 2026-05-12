"""KPI helpers used across forecast, optimization, vendor scoring, and tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

# -----------------------------------------------------------------------------
# Forecast accuracy
# -----------------------------------------------------------------------------


def mape(actual: np.ndarray | pd.Series, forecast: np.ndarray | pd.Series) -> float:
    """Mean Absolute Percentage Error, ignoring zero-actual rows."""
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    mask = a > 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs(f[mask] - a[mask]) / a[mask]))


def wape(actual: np.ndarray | pd.Series, forecast: np.ndarray | pd.Series) -> float:
    """Weighted (sum-based) Absolute Percentage Error."""
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    denom = float(np.sum(a))
    if denom <= 0:
        return float("nan")
    return float(np.sum(np.abs(f - a)) / denom)


def bias(actual: np.ndarray | pd.Series, forecast: np.ndarray | pd.Series) -> float:
    """Mean signed forecast error: positive = over-forecasting."""
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    return float(np.mean(f - a))


# -----------------------------------------------------------------------------
# Operational KPIs
# -----------------------------------------------------------------------------


def fill_rate(
    units_shipped: np.ndarray | pd.Series, units_ordered: np.ndarray | pd.Series
) -> float:
    """Aggregate fill rate: total units shipped / total units ordered."""
    s = float(np.sum(units_shipped))
    o = float(np.sum(units_ordered))
    if o <= 0:
        return float("nan")
    return s / o


def otif_rate(
    promised: pd.Series,
    delivered: pd.Series,
    units_ordered: np.ndarray | pd.Series,
    units_shipped: np.ndarray | pd.Series,
) -> float:
    """Fraction of shipments that are both on-time and in-full."""
    promised = pd.to_datetime(promised)
    delivered = pd.to_datetime(delivered)
    on_time = delivered <= promised
    in_full = np.asarray(units_shipped) >= np.asarray(units_ordered)
    return float(np.mean(on_time & in_full))


def days_of_supply(on_hand: float, avg_daily_demand: float, cap: float = 999.0) -> float:
    """on_hand / avg_daily_demand, capped at ``cap`` when demand approaches zero."""
    if avg_daily_demand <= 0:
        return cap
    return min(on_hand / avg_daily_demand, cap)
