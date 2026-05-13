"""Supply Chain Control Tower -- Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from streamlit_app.utils.data_loader import AIRFLOW_UI_URL, MLFLOW_UI_URL, health_check

st.set_page_config(
    page_title="Supply Chain Control Tower",
    page_icon="SCM",
    layout="wide",
)

st.title("Supply Chain Control Tower")

st.markdown(
    """
    **End-to-end supply-chain analytics with dbt + DuckDB + Airflow + Prophet + OR-Tools**

    A capstone analytics platform that simulates two years of ERP-style supply
    chain operations (500 SKUs, 20 vendors, 5 warehouses), orchestrates the
    daily pipeline with Airflow, builds analytical marts with dbt (incl.
    SCD-2 vendor + SKU snapshots), forecasts demand with Prophet (tracked in
    MLflow), and chooses cost-optimal reorder points with Google OR-Tools.

    Use the sidebar to navigate:

    - **Executive Overview** -- top-line KPIs (OTIF, fill rate, stockout count, inventory $)
    - **Inventory Health** -- days-of-supply distribution, stockout risk heatmap, slow movers
    - **Forecast Accuracy** -- MAPE / WAPE by category, forecast vs actual, link to MLflow
    - **Replenishment** -- OR-Tools optimizer vs textbook safety-stock comparison + cost savings
    - **Vendor Scorecard** -- composite scores, lead-time variance, late shipment trends
    - **Warehouse Performance** -- per-warehouse fulfillment KPIs and backlog aging
    """
)

st.divider()

ok, msg = health_check()
if not ok:
    st.warning(msg)

cols = st.columns(2)
cols[0].link_button("Open MLflow tracking UI", MLFLOW_UI_URL)
cols[1].link_button("Open Airflow webserver", AIRFLOW_UI_URL)

st.caption(
    "Built with dbt + DuckDB, Prophet + MLflow, OR-Tools, Airflow (Docker), Streamlit, GitHub Actions CI."
)
