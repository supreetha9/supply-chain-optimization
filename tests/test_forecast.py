"""Tests for python.src.forecast (Prophet wrapper + MLflow logging).

Uses a temporary file-store MLflow URI so tests don't depend on the Docker
tracking server. The fail-fast behavior of forecast.py is verified by
unsetting MLFLOW_TRACKING_URI in one test.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _synthetic_history(days: int = 200, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    base = 50 + 10 * np.sin(2 * np.pi * np.arange(days) / 7)
    noise = rng.normal(0, 3, days)
    return pd.DataFrame({"ds": dates, "y": np.clip(base + noise, 0, None)})


class TestRequireTrackingUri:
    def test_unset_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from python.src.forecast import require_tracking_uri

        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        with pytest.raises(RuntimeError, match="MLFLOW_TRACKING_URI"):
            require_tracking_uri()

    def test_set_returns_uri(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from python.src.forecast import require_tracking_uri

        monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://example:5000")
        assert require_tracking_uri() == "http://example:5000"


class TestFitProphet:
    def test_horizon_length(self) -> None:
        from python.src.forecast import fit_prophet

        history = _synthetic_history()
        horizon, _, _ = fit_prophet(history, is_seasonal=False, horizon_days=14, holdout_days=30)
        assert len(horizon) == 14
        assert {"ds", "yhat", "yhat_lower", "yhat_upper"} == set(horizon.columns)

    def test_metrics_present(self) -> None:
        from python.src.forecast import fit_prophet

        history = _synthetic_history()
        _, metrics, _ = fit_prophet(history, is_seasonal=False, horizon_days=7, holdout_days=30)
        assert {"mape", "wape", "mean_bias", "observation_count"} <= set(metrics.keys())
        # observation_count must equal holdout
        assert metrics["observation_count"] == 30

    def test_short_history_raises(self) -> None:
        from python.src.forecast import fit_prophet

        history = _synthetic_history(days=20)
        with pytest.raises(ValueError, match="history too short"):
            fit_prophet(history, is_seasonal=False, horizon_days=7, holdout_days=30)

    def test_seasonal_param_propagates(self) -> None:
        from python.src.forecast import fit_prophet

        history = _synthetic_history()
        _, _, params = fit_prophet(history, is_seasonal=True, horizon_days=7, holdout_days=30)
        assert params["seasonality_mode"] == "multiplicative"
        assert params["yearly_seasonality"] is True


class TestForecastAllSmoke:
    """End-to-end smoke test: generate a tiny demand parquet, run forecast_all,
    verify outputs land in the expected format."""

    @pytest.fixture
    def temp_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        # Write a small synthetic dataset that mimics fact_demand_daily +
        # dim_skus, then point forecast.RAW_DIR / FORECAST_DIR at tmp_path.
        from python.src import forecast as fc

        raw_dir = tmp_path / "raw"
        forecast_dir = tmp_path / "forecast"
        raw_dir.mkdir()
        forecast_dir.mkdir()

        rng = np.random.default_rng(0)
        dates = pd.date_range("2024-01-01", periods=200, freq="D")
        rows = []
        for sku_id in ("s_001", "s_002"):
            for wh in ("w_01", "w_02"):
                base = 30 + 5 * np.sin(2 * np.pi * np.arange(len(dates)) / 7)
                rows.append(
                    pd.DataFrame(
                        {
                            "demand_date": dates,
                            "sku_id": sku_id,
                            "warehouse_id": wh,
                            "units_demanded": np.clip(
                                base + rng.normal(0, 2, len(dates)), 0, None
                            ).astype(int),
                        }
                    )
                )
        pd.concat(rows).to_parquet(raw_dir / "fact_demand_daily.parquet", index=False)
        pd.DataFrame(
            {
                "sku_id": ["s_001", "s_002"],
                "abc_class": ["A", "B"],
                "seasonality_flag": [True, False],
            }
        ).to_parquet(raw_dir / "dim_skus.parquet", index=False)

        monkeypatch.setattr(fc, "RAW_DIR", raw_dir)
        monkeypatch.setattr(fc, "FORECAST_DIR", forecast_dir)
        monkeypatch.setattr(fc, "FORECAST_PATH", forecast_dir / "fact_demand_forecast.parquet")
        return tmp_path

    def test_smoke(self, temp_data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from python.src import forecast as fc

        monkeypatch.setenv("MLFLOW_TRACKING_URI", f"file:{temp_data / 'mlruns'}")

        forecast = fc.forecast_all(top_n=2, horizon_days=7, holdout_days=30)
        out = fc.persist_forecast(forecast)

        assert out.exists()
        loaded = pd.read_parquet(out)
        assert {
            "forecast_date",
            "sku_id",
            "warehouse_id",
            "yhat",
            "yhat_lower",
            "yhat_upper",
            "model_run_id",
        } == set(loaded.columns)
        assert len(loaded) == 7 * 2  # 7-day horizon x 2 series
        assert loaded["model_run_id"].nunique() == 1
