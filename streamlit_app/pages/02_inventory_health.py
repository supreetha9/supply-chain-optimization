"""Inventory Health -- days of supply, stockout risk heatmap, slow movers."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from streamlit_app.utils.data_loader import health_check, load_inventory_health

st.set_page_config(page_title="Inventory Health", layout="wide")
st.title("Inventory Health")

ok, msg = health_check()
if not ok:
    st.warning(msg)
    st.stop()

inv = load_inventory_health()

regions = sorted(inv["region"].dropna().unique())
abc_classes = sorted(inv["abc_class"].dropna().unique())

c1, c2 = st.columns(2)
region_filter = c1.multiselect("Region", regions, default=regions)
abc_filter = c2.multiselect("ABC class", abc_classes, default=abc_classes)

filtered = inv[inv["region"].isin(region_filter) & inv["abc_class"].isin(abc_filter)]
if filtered.empty:
    st.info("No SKUs match your filters.")
    st.stop()

# Days of supply distribution
fig = px.histogram(
    filtered,
    x="days_of_supply_30d",
    nbins=50,
    color="abc_class",
    title="Distribution of 30-day days-of-supply",
    log_y=True,
)
fig.update_layout(
    xaxis_title="Days of supply (30d demand)", yaxis_title="SKU x warehouse pairs (log)"
)
st.plotly_chart(fig, use_container_width=True)

# Stockout risk heatmap (region x abc_class)
heat = filtered.groupby(["region", "abc_class"])["stockout_risk_score"].mean().reset_index()
fig2 = px.density_heatmap(
    heat,
    x="abc_class",
    y="region",
    z="stockout_risk_score",
    color_continuous_scale="RdYlGn_r",
    range_color=[0, 1],
    title="Mean stockout risk score by region x ABC class",
    text_auto=".2f",
)
st.plotly_chart(fig2, use_container_width=True)

# Top slow-movers
slow = filtered[filtered["is_slow_moving"]].nlargest(20, "on_hand_value_usd")
st.subheader("Top 20 slow-moving SKUs by on-hand value")
if slow.empty:
    st.info("No slow-moving SKUs detected for the current filters.")
else:
    st.dataframe(
        slow[
            [
                "sku_id",
                "sku_name",
                "category",
                "abc_class",
                "warehouse_name",
                "on_hand_units",
                "days_of_supply_30d",
                "on_hand_value_usd",
            ]
        ].rename(columns={"on_hand_value_usd": "on_hand_value_$"}),
        use_container_width=True,
    )
