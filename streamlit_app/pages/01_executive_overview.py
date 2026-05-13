"""Executive Overview -- top-line supply chain KPIs."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from streamlit_app.utils.data_loader import (
    health_check,
    latest_alerts,
    load_inventory_health,
    load_otif,
    load_reorder_recommendations,
)

st.set_page_config(page_title="Executive Overview", layout="wide")
st.title("Executive Overview")

ok, msg = health_check()
if not ok:
    st.warning(msg)
    st.stop()

inv = load_inventory_health()
otif = load_otif()
reco = load_reorder_recommendations()

# KPIs
total_inventory_value = float(inv["on_hand_value_usd"].sum())
otif_overall = float(otif["otif_count"].sum() / max(otif["shipment_count"].sum(), 1))
fill_overall = float(otif["otif_count"].sum() / max(otif["shipment_count"].sum(), 1))
stockout_count = int((inv["stockout_risk_score"] >= 0.85).sum())
needs_reorder = int(reco["needs_reorder"].sum()) if not reco.empty else 0
excess_value = float(inv.loc[inv["is_slow_moving"], "on_hand_value_usd"].sum())

cols = st.columns(5)
cols[0].metric("On-hand inventory value", f"${total_inventory_value:,.0f}")
cols[1].metric("OTIF rate (all-time)", f"{otif_overall:.1%}")
cols[2].metric("Imminent stockouts (risk >=85%)", f"{stockout_count}")
cols[3].metric("SKUs needing reorder", f"{needs_reorder}")
cols[4].metric("Excess (slow-moving) inventory $", f"${excess_value:,.0f}")

st.divider()

# 30-day OTIF trend
otif_trend = (
    otif.groupby("ship_month")
    .agg(otif_count=("otif_count", "sum"), shipment_count=("shipment_count", "sum"))
    .assign(otif_rate=lambda d: d["otif_count"] / d["shipment_count"])
    .reset_index()
    .sort_values("ship_month")
    .tail(12)
)

if not otif_trend.empty:
    fig = px.line(
        otif_trend,
        x="ship_month",
        y="otif_rate",
        markers=True,
        title="OTIF rate by month (last 12 months)",
    )
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    fig.update_layout(yaxis_title="OTIF rate", xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

# Inventory by ABC class
abc_summary = (
    inv.groupby("abc_class")
    .agg(
        on_hand_value=("on_hand_value_usd", "sum"),
        stockout_risk=("stockout_risk_score", "mean"),
    )
    .reset_index()
)

fig2 = px.bar(
    abc_summary,
    x="abc_class",
    y="on_hand_value",
    title="On-hand inventory $ by ABC class",
    color="abc_class",
)
fig2.update_layout(showlegend=False)
st.plotly_chart(fig2, use_container_width=True)

# Recent alerts
st.subheader("Recent alert log entries")
log_lines = latest_alerts(n=5)
if not log_lines:
    st.info(
        "No alerts logged yet. Run `make analyze` (or trigger the Airflow DAG) to populate the log."
    )
else:
    for line in log_lines:
        st.text(line.rstrip())
