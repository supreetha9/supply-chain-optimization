"""Tests for the OR-Tools reorder-point optimizer."""

from __future__ import annotations

import math

import pytest

from python.src.optimization import OptimizationInput, _expected_costs, optimize_one


def _make_input(**overrides) -> OptimizationInput:
    base = dict(
        sku_id="s_test",
        warehouse_id="w_test",
        avg_daily_demand=10.0,
        std_daily_demand=3.0,
        lead_time_days=14.0,
        holding_cost_per_unit_per_day=0.05,
        stockout_penalty_per_unit=5.0,
        target_service_level=0.95,
        capacity_units=10_000,
    )
    base.update(overrides)
    return OptimizationInput(**base)


class TestExpectedCosts:
    def test_costs_nonnegative(self) -> None:
        h, s, t = _expected_costs(
            reorder_point=200,
            avg_daily_demand=10.0,
            std_daily_demand=3.0,
            lead_time_days=14.0,
            holding_cost_per_unit_per_day=0.05,
            stockout_penalty_per_unit=5.0,
        )
        assert h >= 0
        assert s >= 0
        assert math.isclose(t, h + s)

    def test_higher_reorder_point_lowers_stockout(self) -> None:
        kw = dict(
            avg_daily_demand=10.0,
            std_daily_demand=3.0,
            lead_time_days=14.0,
            holding_cost_per_unit_per_day=0.05,
            stockout_penalty_per_unit=5.0,
        )
        _, s_low, _ = _expected_costs(reorder_point=140, **kw)
        _, s_high, _ = _expected_costs(reorder_point=200, **kw)
        assert s_high < s_low

    def test_higher_reorder_point_raises_holding(self) -> None:
        kw = dict(
            avg_daily_demand=10.0,
            std_daily_demand=3.0,
            lead_time_days=14.0,
            holding_cost_per_unit_per_day=0.05,
            stockout_penalty_per_unit=5.0,
        )
        h_low, _, _ = _expected_costs(reorder_point=140, **kw)
        h_high, _, _ = _expected_costs(reorder_point=200, **kw)
        assert h_high > h_low


class TestOptimizeOne:
    def test_returns_valid_result(self) -> None:
        result = optimize_one(_make_input())
        assert result.reorder_point_optimized > 0
        assert result.expected_total_cost >= 0
        assert math.isclose(
            result.expected_total_cost,
            result.expected_holding_cost + result.expected_stockout_cost,
            rel_tol=1e-6,
        )

    def test_service_level_floor_respected(self) -> None:
        """Optimizer's R must be >= the service-level floor (mu_L + z * sigma_L)."""
        from scipy.stats import norm

        inp = _make_input(target_service_level=0.95)
        result = optimize_one(inp)

        z = norm.ppf(0.95)
        mu_l = inp.avg_daily_demand * inp.lead_time_days
        sigma_l = inp.std_daily_demand * (inp.lead_time_days**0.5)
        floor = mu_l + z * sigma_l
        assert result.reorder_point_optimized + 1e-6 >= floor

    def test_textbook_baseline_present(self) -> None:
        result = optimize_one(_make_input())
        assert result.reorder_point_textbook > 0

    def test_higher_stockout_penalty_higher_reorder(self) -> None:
        cheap_stockout = optimize_one(_make_input(stockout_penalty_per_unit=1.0))
        expensive_stockout = optimize_one(_make_input(stockout_penalty_per_unit=50.0))
        assert expensive_stockout.reorder_point_optimized >= cheap_stockout.reorder_point_optimized

    def test_zero_variance_optimum_close_to_mean(self) -> None:
        """If demand has no variance, optimal R is just mu_L (plus tiny floor)."""
        result = optimize_one(_make_input(std_daily_demand=0.0))
        mu_l = 10.0 * 14.0
        # R can be slightly above mu_L because of the min sigma_l = 1e-9
        assert result.reorder_point_optimized >= mu_l - 1
        assert result.reorder_point_optimized <= mu_l + 5

    @pytest.mark.parametrize("service_level", [0.90, 0.95, 0.98])
    def test_higher_service_level_higher_reorder(self, service_level: float) -> None:
        baseline = optimize_one(_make_input(target_service_level=0.90))
        higher = optimize_one(_make_input(target_service_level=service_level))
        assert higher.reorder_point_optimized + 1e-6 >= baseline.reorder_point_optimized
