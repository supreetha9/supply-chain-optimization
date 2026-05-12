"""Tests for the composite vendor scorer."""

from __future__ import annotations

import pandas as pd
import pytest

from python.src.vendor_scoring import DEFAULT_WEIGHTS, ScoreWeights, compute_scores


def _vendor_row(**overrides) -> dict:
    base = dict(
        vendor_id="v_001",
        vendor_name="Acme",
        contract_lead_time_days=20,
        actual_lead_time_avg=20.0,
        actual_lead_time_std=2.0,
        late_arrival_rate=0.05,
        defect_rate=0.01,
    )
    base.update(overrides)
    return base


def test_score_bounded_in_0_100() -> None:
    df = pd.DataFrame(
        [
            _vendor_row(
                vendor_id="v_perfect",
                actual_lead_time_avg=10,
                actual_lead_time_std=0,
                late_arrival_rate=0,
                defect_rate=0,
            ),
            _vendor_row(
                vendor_id="v_terrible",
                contract_lead_time_days=10,
                actual_lead_time_avg=40,
                actual_lead_time_std=20,
                late_arrival_rate=0.95,
                defect_rate=0.50,
            ),
        ]
    )
    out = compute_scores(df)
    assert (out["composite_score"] >= 0).all()
    assert (out["composite_score"] <= 100).all()


def test_perfect_vendor_scores_zero() -> None:
    df = pd.DataFrame(
        [
            _vendor_row(
                actual_lead_time_avg=20,
                actual_lead_time_std=0,
                late_arrival_rate=0.0,
                defect_rate=0.0,
            )
        ]
    )
    out = compute_scores(df)
    assert out.iloc[0]["composite_score"] == pytest.approx(0.0, abs=1e-6)


def test_lower_is_better_ranking() -> None:
    df = pd.DataFrame(
        [
            _vendor_row(
                vendor_id="v_good",
                actual_lead_time_avg=20,
                actual_lead_time_std=0,
                late_arrival_rate=0.0,
                defect_rate=0.001,
            ),
            _vendor_row(
                vendor_id="v_bad",
                actual_lead_time_avg=30,
                actual_lead_time_std=10,
                late_arrival_rate=0.50,
                defect_rate=0.10,
            ),
        ]
    )
    out = compute_scores(df)
    # First row (best score) must be v_good
    assert out.iloc[0]["vendor_id"] == "v_good"
    assert out.iloc[-1]["vendor_id"] == "v_bad"
    assert out.iloc[0]["composite_score"] < out.iloc[-1]["composite_score"]


def test_tied_vendors_same_score() -> None:
    df = pd.DataFrame(
        [
            _vendor_row(vendor_id="a"),
            _vendor_row(vendor_id="b"),
        ]
    )
    out = compute_scores(df)
    s = out["composite_score"].to_numpy()
    assert s[0] == s[1]


def test_missing_required_column_raises() -> None:
    df = pd.DataFrame([{"vendor_id": "x", "vendor_name": "x"}])
    with pytest.raises(ValueError):
        compute_scores(df)


def test_weights_sum_to_one() -> None:
    assert pytest.approx(DEFAULT_WEIGHTS.total(), abs=1e-9) == 1.0


def test_custom_weights() -> None:
    w = ScoreWeights(
        lead_time_overshoot=0.50,
        late_arrival_rate=0.50,
        defect_rate=0.0,
        variance_ratio=0.0,
    )
    df = pd.DataFrame(
        [
            _vendor_row(defect_rate=0.50),  # huge defect
            _vendor_row(defect_rate=0.001),  # tiny defect
        ]
    )
    out = compute_scores(df, weights=w)
    # With defect weight=0, the scores should be equal
    assert out.iloc[0]["composite_score"] == pytest.approx(out.iloc[1]["composite_score"])


def test_nan_lead_time_avg_filled_with_contract() -> None:
    df = pd.DataFrame([_vendor_row(actual_lead_time_avg=None)])
    out = compute_scores(df)
    # No overshoot since actual_lead_time_avg falls back to contract
    assert out.iloc[0]["score_lead_time_overshoot"] == 0.0
