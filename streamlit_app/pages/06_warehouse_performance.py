"""Warehouse Performance -- per-warehouse fulfillment KPIs and backlog aging."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from streamlit_app.utils.data_loader import (
    health_check,
    load_otif,
    load_warehouse_performance,
)

st.set_page_config(page_title="Warehouse Performance", layout="wide")
st.title("Warehouse Performance")

ok, msg = health_check()
if not ok:
    st.warning(msg)
    st.stop()

wh = load_warehouse_performance()
otif = load_otif()

if wh.empty:
    st.info("No warehouse data yet. Run `make pipeline`.")
    st.stop()

# Headline KPIs (totals across warehouses)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Shipments (90d)", f"{int(wh['shipment_count_90d'].sum()):,}")
c2.metric("Units shipped (90d)", f"{int(wh['units_shipped_90d'].sum()):,}")
c3.metric("Avg on-time rate (90d)", f"{wh['on_time_rate_90d'].mean():.1%}")
c4.metric("Backlog units (30d)", f"{int(wh['backlog_units_30d'].sum()):,}")

st.divider()

# Per-warehouse comparison
fig = px.bar(
    wh.sort_values("on_time_rate_90d", ascending=False),
    x="warehouse_name",
    y="on_time_rate_90d",
    color="region",
    title="On-time rate by warehouse (last 90 days)",
    hover_data=["shipment_count_90d", "units_shipped_90d"],
)
fig.update_yaxes(tickformat=".0%")
st.plotly_chart(fig, use_container_width=True)

# Backlog by warehouse
fig2 = px.bar(
    wh.sort_values("backlog_units_30d", ascending=False),
    x="warehouse_name",
    y="backlog_units_30d",
    color="region",
    title="Backlog (units, last 30 days)",
)
st.plotly_chart(fig2, use_container_width=True)

# OTIF by region trend
otif_trend = (
    otif.groupby(["region", "ship_month"])
    .agg(
        otif_count=("otif_count", "sum"),
        shipment_count=("shipment_count", "sum"),
    )
    .reset_index()
)
otif_trend["otif_rate"] = otif_trend["otif_count"] / otif_trend["shipment_count"]

fig3 = px.line(
    otif_trend.sort_values("ship_month"),
    x="ship_month",
    y="otif_rate",
    color="region",
    markers=True,
    title="OTIF rate by region (monthly)",
)
fig3.update_yaxes(tickformat=".0%", range=[0, 1])
st.plotly_chart(fig3, use_container_width=True)
