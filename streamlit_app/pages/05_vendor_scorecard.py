"""Vendor Scorecard -- composite score, lead-time variance, late shipment trends."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from streamlit_app.utils.data_loader import (
    health_check,
    load_vendor_scorecard,
    load_vendor_scores_artifact,
)

st.set_page_config(page_title="Vendor Scorecard", layout="wide")
st.title("Vendor Scorecard")

ok, msg = health_check()
if not ok:
    st.warning(msg)
    st.stop()

scorecard = load_vendor_scorecard()
scores = load_vendor_scores_artifact()

if scorecard.empty:
    st.info("No vendor data yet. Run `make pipeline`.")
    st.stop()

# Use Python-computed scores when present (richer breakdown)
display = (
    scores.merge(
        scorecard[["vendor_id", "country", "total_po_cost_365d", "defect_cost_impact_usd"]],
        on="vendor_id",
        how="left",
    )
    if not scores.empty
    else scorecard
)

# Per-vendor table
st.subheader("Vendor leaderboard (lower composite score is better)")
cols_to_show = [
    "rank" if "rank" in display.columns else None,
    "vendor_id",
    "vendor_name",
    "country",
    "contract_lead_time_days",
    "actual_lead_time_avg",
    "actual_lead_time_std",
    "late_arrival_rate",
    "defect_rate",
    "composite_score",
]
cols_to_show = [c for c in cols_to_show if c is not None and c in display.columns]
st.dataframe(
    display.sort_values("composite_score")[cols_to_show].style.format(
        {
            "actual_lead_time_avg": "{:.1f}",
            "actual_lead_time_std": "{:.2f}",
            "late_arrival_rate": "{:.1%}",
            "defect_rate": "{:.2%}",
            "composite_score": "{:.1f}",
        }
    ),
    use_container_width=True,
)

c1, c2 = st.columns(2)

# Lead-time variance distribution
fig = px.scatter(
    display,
    x="contract_lead_time_days",
    y="actual_lead_time_avg",
    size="actual_lead_time_std",
    color="country",
    hover_name="vendor_name",
    title="Contract vs actual lead time (bubble = variance)",
)
fig.add_shape(
    type="line",
    x0=0,
    y0=0,
    x1=display["contract_lead_time_days"].max(),
    y1=display["contract_lead_time_days"].max(),
    line=dict(dash="dash"),
)
c1.plotly_chart(fig, use_container_width=True)

# Late arrival rate by country
country_summary = (
    display.groupby("country")
    .agg(
        avg_late_rate=("late_arrival_rate", "mean"),
        avg_score=("composite_score", "mean"),
        vendors=("vendor_id", "count"),
    )
    .reset_index()
    .sort_values("avg_late_rate", ascending=False)
)

fig2 = px.bar(
    country_summary,
    x="country",
    y="avg_late_rate",
    color="avg_score",
    color_continuous_scale="RdYlGn_r",
    text="vendors",
    title="Late arrival rate by country",
)
fig2.update_yaxes(tickformat=".1%")
c2.plotly_chart(fig2, use_container_width=True)
