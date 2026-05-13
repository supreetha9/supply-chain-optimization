"""Forecast Accuracy -- MAPE/WAPE, top-N worst SKUs, forecast vs actual."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from streamlit_app.utils.data_loader import (
    MLFLOW_UI_URL,
    health_check,
    load_demand_history,
    load_forecast_accuracy,
    load_forecast_artifact,
)

st.set_page_config(page_title="Forecast Accuracy", layout="wide")
st.title("Forecast Accuracy (Prophet + MLflow)")

ok, msg = health_check()
if not ok:
    st.warning(msg)
    st.stop()

st.link_button("Open MLflow tracking UI", MLFLOW_UI_URL)

acc = load_forecast_accuracy()
forecast = load_forecast_artifact()

if acc.empty or forecast.empty:
    st.info(
        "No forecast accuracy data yet. Run:\n\n"
        "    export MLFLOW_TRACKING_URI=http://localhost:5000\n"
        "    make forecast && make dbt-build-post"
    )
    st.stop()

# MAPE by category
by_cat = (
    acc.groupby("category")
    .agg(
        mape=("mape", "mean"),
        wape=("wape", "mean"),
        series_count=("sku_id", "nunique"),
    )
    .reset_index()
    .sort_values("mape", ascending=False)
)

st.subheader("MAPE / WAPE by category")
fig = px.bar(
    by_cat,
    x="category",
    y="mape",
    color="abc_class" if "abc_class" in by_cat else None,
    title="Mean MAPE by SKU category",
    text_auto=".2%",
)
fig.update_yaxes(tickformat=".0%")
st.plotly_chart(fig, use_container_width=True)

# Top 10 worst-forecasted SKUs
worst = acc.nlargest(10, "wape")
st.subheader("Top 10 worst-forecasted SKUs (by WAPE)")
st.dataframe(
    worst[
        [
            "sku_id",
            "sku_name",
            "category",
            "abc_class",
            "warehouse_id",
            "observation_count",
            "mape",
            "wape",
            "mean_bias",
            "coverage_95",
        ]
    ].style.format({"mape": "{:.1%}", "wape": "{:.1%}", "coverage_95": "{:.0%}"}),
    use_container_width=True,
)

# Forecast vs actual chart for a selectable SKU
st.subheader("Forecast vs actual for a selected SKU")
options = forecast.groupby(["sku_id", "warehouse_id"]).size().reset_index().rename(columns={0: "n"})
options["label"] = options["sku_id"] + " @ " + options["warehouse_id"]

choice = st.selectbox("Pick a SKU x warehouse", options["label"], index=0)
sku_id, warehouse_id = choice.split(" @ ")

history = load_demand_history()
hist_slice = history[
    (history["sku_id"] == sku_id) & (history["warehouse_id"] == warehouse_id)
].tail(120)
fcst_slice = forecast[(forecast["sku_id"] == sku_id) & (forecast["warehouse_id"] == warehouse_id)]

combined = pd.concat(
    [
        hist_slice.rename(columns={"demand_date": "ds", "units_demanded": "y"})[["ds", "y"]].assign(
            kind="actual"
        ),
        fcst_slice.rename(columns={"forecast_date": "ds", "yhat": "y"})[["ds", "y"]].assign(
            kind="forecast"
        ),
    ]
)
fig2 = px.line(
    combined,
    x="ds",
    y="y",
    color="kind",
    title=f"{sku_id} @ {warehouse_id}: last 120 days actual + 30 days forecast",
)
st.plotly_chart(fig2, use_container_width=True)

# Confidence band overlay
if not fcst_slice.empty:
    band = fcst_slice[["forecast_date", "yhat_lower", "yhat_upper"]].rename(
        columns={"forecast_date": "ds"}
    )
    st.caption("Forecast 80% confidence band:")
    st.dataframe(band, use_container_width=True)
