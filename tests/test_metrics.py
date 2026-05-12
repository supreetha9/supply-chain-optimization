"""Unit tests for KPI helpers in python.src.metrics."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from python.src.metrics import bias, days_of_supply, fill_rate, mape, otif_rate, wape


class TestForecastAccuracy:
    def test_mape_perfect_forecast(self) -> None:
        assert mape([10, 20, 30], [10, 20, 30]) == 0.0

    def test_mape_known_value(self) -> None:
        # Errors of 1 each on actuals 10, 20, 30: (1/10 + 1/20 + 1/30) / 3 = 0.0611...
        result = mape([10, 20, 30], [11, 21, 31])
        assert math.isclose(result, (0.10 + 0.05 + 1 / 30) / 3, rel_tol=1e-6)

    def test_mape_skips_zero_actual(self) -> None:
        # Zero rows are excluded; nonzero rows have 50% error.
        assert math.isclose(mape([0, 0, 10], [5, 5, 15]), 0.5)

    def test_mape_nan_when_all_zero(self) -> None:
        assert math.isnan(mape([0, 0, 0], [1, 2, 3]))

    def test_wape_known(self) -> None:
        # |11-10| + |19-20| + |31-30| = 3; sum actual = 60; wape = 0.05
        assert math.isclose(wape([10, 20, 30], [11, 19, 31]), 3 / 60)

    def test_wape_nan_when_actual_zero(self) -> None:
        assert math.isnan(wape([0, 0], [1, 2]))

    def test_bias_signed(self) -> None:
        # Forecast over by 2, under by 2 -> mean signed error = 0
        assert bias([10, 20], [12, 18]) == 0.0
        # Consistent over-forecast
        assert bias([10, 20], [11, 22]) == 1.5


class TestOperationalKpis:
    def test_fill_rate_simple(self) -> None:
        assert fill_rate([5, 10], [10, 10]) == 0.75

    def test_fill_rate_nan_when_zero_orders(self) -> None:
        assert math.isnan(fill_rate([0], [0]))

    def test_otif_rate(self) -> None:
        df = pd.DataFrame(
            {
                "promised": ["2025-01-05", "2025-01-05", "2025-01-05"],
                "delivered": ["2025-01-04", "2025-01-06", "2025-01-04"],
                "units_ordered": [10, 10, 10],
                "units_shipped": [10, 10, 8],
            }
        )
        # Row 0: on-time + in-full -> True
        # Row 1: late -> False
        # Row 2: short -> False
        result = otif_rate(
            df["promised"], df["delivered"], df["units_ordered"], df["units_shipped"]
        )
        assert math.isclose(result, 1 / 3)

    def test_days_of_supply(self) -> None:
        assert days_of_supply(100, 10) == 10.0
        assert days_of_supply(100, 0) == 999.0
        assert days_of_supply(100, 0.0001) == 999.0
        assert days_of_supply(0, 10) == 0.0


@pytest.mark.parametrize(
    "actual,forecast,expected",
    [
        (np.array([10.0]), np.array([10.0]), 0.0),
        (np.array([10.0]), np.array([15.0]), 0.5),
    ],
)
def test_mape_array_inputs(actual: np.ndarray, forecast: np.ndarray, expected: float) -> None:
    assert math.isclose(mape(actual, forecast), expected)
