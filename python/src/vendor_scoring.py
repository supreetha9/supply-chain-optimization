"""Composite vendor scorer.

Reads vendor lead-time + late-arrival + defect data from the dbt-built
warehouse, computes a 0-100 composite score (lower = better), and writes
the result to ``data/forecast/vendor_scores.parquet`` for the dashboard.

The score blends four normalized components:

  1. Lead-time overshoot  (actual vs contracted)        weight 0.30
  2. Late-arrival rate                                  weight 0.30
  3. Defect rate                                        weight 0.30
  4. Lead-time variance                                 weight 0.10

Each component is clipped to [0, 100] before weighting so a catastrophic
single component can't push the score below zero.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = ROOT / "data" / "supply.duckdb"
OUT_PATH = ROOT / "data" / "forecast" / "vendor_scores.parquet"

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScoreWeights:
    lead_time_overshoot: float = 0.30
    late_arrival_rate: float = 0.30
    defect_rate: float = 0.30
    variance_ratio: float = 0.10

    def total(self) -> float:
        return (
            self.lead_time_overshoot
            + self.late_arrival_rate
            + self.defect_rate
            + self.variance_ratio
        )


DEFAULT_WEIGHTS = ScoreWeights()


def _normalize_overshoot(actual_lead_time: pd.Series, contract_lead_time: pd.Series) -> pd.Series:
    overshoot = (actual_lead_time - contract_lead_time) / contract_lead_time.replace({0: np.nan})
    return overshoot.clip(lower=0).fillna(0) * 100


def _normalize_variance(actual_std: pd.Series, contract_lead_time: pd.Series) -> pd.Series:
    return (actual_std / contract_lead_time.replace({0: np.nan})).fillna(0).clip(lower=0) * 100


def compute_scores(
    df: pd.DataFrame,
    *,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
) -> pd.DataFrame:
    """Compute composite scores from a vendor-lead-time DataFrame.

    Required columns:
      vendor_id, vendor_name, contract_lead_time_days,
      actual_lead_time_avg, actual_lead_time_std,
      late_arrival_rate, defect_rate
    """
    required = {
        "vendor_id",
        "vendor_name",
        "contract_lead_time_days",
        "actual_lead_time_avg",
        "actual_lead_time_std",
        "late_arrival_rate",
        "defect_rate",
    }
    missing = required - set(df.columns)
    if missing:
        msg = f"compute_scores missing columns: {missing}"
        raise ValueError(msg)

    df = df.copy()
    df["actual_lead_time_avg"] = df["actual_lead_time_avg"].fillna(df["contract_lead_time_days"])
    df["actual_lead_time_std"] = df["actual_lead_time_std"].fillna(0)
    df["late_arrival_rate"] = df["late_arrival_rate"].fillna(0)

    overshoot = _normalize_overshoot(
        df["actual_lead_time_avg"], df["contract_lead_time_days"]
    ).clip(0, 100)
    late = (df["late_arrival_rate"] * 100).clip(0, 100)
    defect = (df["defect_rate"] * 1000).clip(0, 100)
    variance = _normalize_variance(df["actual_lead_time_std"], df["contract_lead_time_days"]).clip(
        0, 100
    )

    df["score_lead_time_overshoot"] = overshoot
    df["score_late_arrival"] = late
    df["score_defect"] = defect
    df["score_variance"] = variance

    df["composite_score"] = (
        overshoot * weights.lead_time_overshoot
        + late * weights.late_arrival_rate
        + defect * weights.defect_rate
        + variance * weights.variance_ratio
    ).clip(0, 100)

    df["rank"] = df["composite_score"].rank(method="min").astype(int)
    return df.sort_values("composite_score").reset_index(drop=True)


def _load_inputs(duckdb_path: Path = DUCKDB_PATH) -> pd.DataFrame:
    sql = """
    select
        s.vendor_id,
        s.vendor_name,
        s.contract_lead_time_days,
        s.actual_lead_time_avg,
        s.actual_lead_time_std,
        s.late_arrival_rate,
        s.defect_rate
    from main_marts.mart_vendor_scorecard s
    """
    with duckdb.connect(str(duckdb_path), read_only=True) as conn:
        return conn.execute(sql).df()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Composite vendor scorer.")
    parser.add_argument("--duckdb", type=Path, default=DUCKDB_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    df = _load_inputs(args.duckdb)
    scored = compute_scores(df)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(args.out, index=False)
    logger.info("Scored %d vendors -> %s", len(scored), args.out)
    logger.info(
        "Best vendor (score %.2f): %s",
        float(scored.iloc[0]["composite_score"]),
        scored.iloc[0]["vendor_name"],
    )
    logger.info(
        "Worst vendor (score %.2f): %s",
        float(scored.iloc[-1]["composite_score"]),
        scored.iloc[-1]["vendor_name"],
    )


if __name__ == "__main__":
    main()
