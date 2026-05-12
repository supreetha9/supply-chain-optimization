"""Textbook safety-stock formula.

Implements the canonical newsvendor / cycle-stock formula used as the
benchmark in the Streamlit optimizer-vs-formula comparison. The OR-Tools
optimizer is shown to outperform this on simulated cost.

Safety stock = z_score(service_level) * sqrt(lead_time_days) * std_demand

Reorder point = avg_daily_demand * lead_time_days + safety_stock
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy.stats import norm


@dataclass(slots=True)
class SafetyStockResult:
    safety_stock: float
    reorder_point: float
    z_score: float


def z_for_service_level(service_level: float) -> float:
    """Return the z-score (one-sided) for a target service level in (0, 1)."""
    if not 0 < service_level < 1:
        msg = f"service_level must be in (0, 1); got {service_level}"
        raise ValueError(msg)
    return float(norm.ppf(service_level))


def safety_stock_textbook(
    *,
    avg_daily_demand: float,
    std_daily_demand: float,
    lead_time_days: float,
    service_level: float,
) -> SafetyStockResult:
    """Standard cycle-stock + safety-stock formula.

    Assumes demand variability dominates lead-time variability (the simple
    case taught in any inventory-management textbook).
    """
    if avg_daily_demand < 0 or std_daily_demand < 0 or lead_time_days < 0:
        msg = "avg_daily_demand, std_daily_demand, lead_time_days must be >= 0"
        raise ValueError(msg)

    z = z_for_service_level(service_level)
    safety = z * (lead_time_days**0.5) * std_daily_demand
    reorder = avg_daily_demand * lead_time_days + safety
    return SafetyStockResult(
        safety_stock=float(safety),
        reorder_point=float(reorder),
        z_score=float(z),
    )


def safety_stock_with_lead_time_variance(
    *,
    avg_daily_demand: float,
    std_daily_demand: float,
    lead_time_days: float,
    std_lead_time_days: float,
    service_level: float,
) -> SafetyStockResult:
    """Combined-variance formula when lead-time itself is stochastic.

    safety = z * sqrt(L * sigma_d^2 + d^2 * sigma_L^2)
    """
    if std_lead_time_days < 0:
        msg = "std_lead_time_days must be >= 0"
        raise ValueError(msg)

    z = z_for_service_level(service_level)
    variance = lead_time_days * (std_daily_demand**2) + (avg_daily_demand**2) * (
        std_lead_time_days**2
    )
    safety = z * (variance**0.5)
    reorder = avg_daily_demand * lead_time_days + safety
    return SafetyStockResult(
        safety_stock=float(safety),
        reorder_point=float(reorder),
        z_score=float(z),
    )
