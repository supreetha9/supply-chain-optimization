"""Replenishment -- OR-Tools optimizer vs textbook safety-stock comparison."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from streamlit_app.utils.data_loader import (
    health_check,
    load_reorder_optimized,
    load_reorder_recommendations,
)

st.set_page_config(page_title="Replenishment", layout="wide")
st.title("Replenishment (OR-Tools vs Textbook)")

ok, msg = health_check()
if not ok:
    st.warning(msg)
    st.stop()

mart = load_reorder_recommendations()
opt = load_reorder_optimized()

if mart.empty:
    st.info("No reorder recommendations yet. Run `make pipeline`.")
    st.stop()

# Combined view
joined = mart.merge(
    opt[
        [
            "sku_id",
            "warehouse_id",
            "reorder_point_optimized",
            "reorder_point_textbook",
            "expected_total_cost",
            "cost_savings_vs_textbook",
        ]
    ],
    on=["sku_id", "warehouse_id"],
    how="left",
)

# Headline cost saving
total_savings = float(joined["cost_savings_vs_textbook"].fillna(0).sum())
total_cost = float(joined["expected_total_cost"].fillna(0).sum())
to_reorder = int(joined["needs_reorder"].sum())

c1, c2, c3 = st.columns(3)
c1.metric("OR-Tools savings vs textbook", f"${total_savings:,.0f}")
c2.metric("Total expected cost (optimized)", f"${total_cost:,.0f}")
c3.metric("SKUs flagged for reorder", f"{to_reorder}")

st.divider()

# Comparison toggle
mode = st.radio(
    "Compare reorder points:", ["Both", "OR-Tools only", "Textbook only"], horizontal=True
)

abc_filter = st.multiselect(
    "ABC class",
    options=sorted(joined["abc_class"].dropna().unique()),
    default=sorted(joined["abc_class"].dropna().unique()),
)
filtered = joined[joined["abc_class"].isin(abc_filter)].copy()

if mode == "Both":
    long = filtered.melt(
        id_vars=["sku_id", "warehouse_id", "abc_class"],
        value_vars=["reorder_point_textbook", "reorder_point_optimized"],
        var_name="method",
        value_name="reorder_point",
    )
    fig = px.box(
        long,
        x="abc_class",
        y="reorder_point",
        color="method",
        title="Reorder point distribution: OR-Tools vs textbook (by ABC class)",
    )
elif mode == "OR-Tools only":
    fig = px.box(
        filtered,
        x="abc_class",
        y="reorder_point_optimized",
        title="OR-Tools reorder point by ABC class",
    )
else:
    fig = px.box(
        filtered,
        x="abc_class",
        y="reorder_point_textbook",
        title="Textbook safety-stock reorder point by ABC class",
    )
st.plotly_chart(fig, use_container_width=True)

# Reorder candidates table
st.subheader("Reorder candidates (needs_reorder = TRUE)")
to_show = filtered[filtered["needs_reorder"]].nlargest(50, "cost_savings_vs_textbook")
st.dataframe(
    to_show[
        [
            "sku_id",
            "sku_name",
            "category",
            "abc_class",
            "warehouse_id",
            "inventory_position",
            "reorder_point_textbook",
            "reorder_point_optimized",
            "expected_total_cost",
            "cost_savings_vs_textbook",
        ]
    ].style.format(
        {
            "reorder_point_textbook": "{:.0f}",
            "reorder_point_optimized": "{:.0f}",
            "expected_total_cost": "${:,.2f}",
            "cost_savings_vs_textbook": "${:,.2f}",
        }
    ),
    use_container_width=True,
)
