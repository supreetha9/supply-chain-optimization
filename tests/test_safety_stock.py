"""Tests for the textbook safety-stock formula."""

from __future__ import annotations

import math

import pytest

from python.src.safety_stock import (
    safety_stock_textbook,
    safety_stock_with_lead_time_variance,
    z_for_service_level,
)


class TestZScore:
    @pytest.mark.parametrize(
        "sl,expected_z",
        [
            (0.50, 0.0),
            (0.95, 1.6448),
            (0.99, 2.3263),
        ],
    )
    def test_known_values(self, sl: float, expected_z: float) -> None:
        assert math.isclose(z_for_service_level(sl), expected_z, rel_tol=1e-3)

    @pytest.mark.parametrize("sl", [0.0, 1.0, -0.1, 1.5])
    def test_invalid_service_level(self, sl: float) -> None:
        with pytest.raises(ValueError):
            z_for_service_level(sl)


class TestTextbookFormula:
    def test_zero_demand_zero_safety(self) -> None:
        result = safety_stock_textbook(
            avg_daily_demand=0.0,
            std_daily_demand=0.0,
            lead_time_days=10.0,
            service_level=0.95,
        )
        assert result.safety_stock == 0.0
        assert result.reorder_point == 0.0

    def test_known_calculation(self) -> None:
        # z=1.65 (95%), L=16, sigma=5
        # safety = 1.65 * sqrt(16) * 5 = 33
        # reorder = 10 * 16 + 33 = 193
        result = safety_stock_textbook(
            avg_daily_demand=10.0,
            std_daily_demand=5.0,
            lead_time_days=16.0,
            service_level=0.95,
        )
        assert math.isclose(result.safety_stock, 1.6448 * 4 * 5, rel_tol=1e-3)
        assert math.isclose(result.reorder_point, 160 + result.safety_stock, rel_tol=1e-6)

    def test_higher_service_level_higher_safety(self) -> None:
        common = {
            "avg_daily_demand": 10.0,
            "std_daily_demand": 5.0,
            "lead_time_days": 14.0,
        }
        s90 = safety_stock_textbook(service_level=0.90, **common)
        s95 = safety_stock_textbook(service_level=0.95, **common)
        s99 = safety_stock_textbook(service_level=0.99, **common)
        assert s90.safety_stock < s95.safety_stock < s99.safety_stock

    def test_longer_lead_time_higher_safety(self) -> None:
        common = {
            "avg_daily_demand": 10.0,
            "std_daily_demand": 5.0,
            "service_level": 0.95,
        }
        s7 = safety_stock_textbook(lead_time_days=7, **common)
        s28 = safety_stock_textbook(lead_time_days=28, **common)
        assert s28.safety_stock > s7.safety_stock

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"avg_daily_demand": -1, "std_daily_demand": 5, "lead_time_days": 10},
            {"avg_daily_demand": 10, "std_daily_demand": -1, "lead_time_days": 10},
            {"avg_daily_demand": 10, "std_daily_demand": 5, "lead_time_days": -1},
        ],
    )
    def test_negative_inputs_rejected(self, kwargs: dict[str, float]) -> None:
        with pytest.raises(ValueError):
            safety_stock_textbook(service_level=0.95, **kwargs)


class TestCombinedVariance:
    def test_collapses_to_textbook_when_lead_time_certain(self) -> None:
        common = dict(
            avg_daily_demand=10.0,
            std_daily_demand=5.0,
            lead_time_days=16.0,
            service_level=0.95,
        )
        textbook = safety_stock_textbook(**common)
        combined = safety_stock_with_lead_time_variance(std_lead_time_days=0.0, **common)
        assert math.isclose(combined.safety_stock, textbook.safety_stock, rel_tol=1e-6)

    def test_lead_time_variance_increases_safety(self) -> None:
        common = dict(
            avg_daily_demand=10.0,
            std_daily_demand=5.0,
            lead_time_days=16.0,
            service_level=0.95,
        )
        zero_var = safety_stock_with_lead_time_variance(std_lead_time_days=0.0, **common)
        with_var = safety_stock_with_lead_time_variance(std_lead_time_days=5.0, **common)
        assert with_var.safety_stock > zero_var.safety_stock
