Executive Summary
=================

Business problem
----------------

Mid-market consumer-goods and B2B distribution operations lose six-to-seven
figures annually to a small number of recurring failure modes: stockouts of
high-velocity SKUs, working capital trapped in slow-moving inventory,
unmonitored vendor lead-time drift, and OTIF misses that erode customer
contracts. Most of those failures are decision problems with structured
analytical answers, but the answers require connecting an ERP, a forecast
model, and an inventory optimizer in the same pipeline.

Solution architecture
---------------------

Two years of synthetic ERP data flow through a daily Airflow pipeline:
``generate -> dbt build (pre-forecast) -> Prophet forecast (MLflow-tracked)
-> dbt build (post-forecast) -> OR-Tools optimization -> vendor scoring ->
alerts``. dbt builds the analytical marts (inventory_health, otif,
vendor_scorecard, warehouse_performance, forecast_accuracy,
reorder_recommendations) plus two SCD-2 snapshots that capture vendor
contract drift over time. A 6-page Streamlit dashboard surfaces every KPI
and lets the user toggle the OR-Tools-vs-textbook reorder comparison.
GitHub Actions CI validates every push.

Top three ROI levers
--------------------

1. **Forecast-driven reorder optimization.** OR-Tools picks reorder points
   that minimize expected holding + stockout cost subject to a per-ABC
   service-level floor. On the synthetic dataset, this saves roughly
   $2-3K per lead-time window vs the textbook safety-stock formula
   applied with a blanket 0.99 service level. At realistic SKU counts the
   per-year impact extrapolates well into six figures.

2. **Vendor scoring with composite metrics.** A single 0-100 number per
   vendor blends lead-time overshoot, late-arrival rate, defect rate, and
   lead-time variance. Procurement leads get a ranked list with one
   click; the SCD-2 snapshot lets them answer *"why did our lead times
   shift in Q3?"* by joining historical POs to the contract terms in
   force on each PO date.

3. **OTIF visibility with dimensional slicing.** Every shipment is
   classified as on-time-in-full / late-only / short-only / late-and-short
   via the ``otif_status`` macro, then aggregated by warehouse x category
   x month. Operations directors see attainment trends with the
   regional/category context that explains *why* it's moving.

Tech stack signal
-----------------

This project is project 4 of a four-project portfolio that progressively
builds production analytics capability:

1. SaaS Growth -- DuckDB + Streamlit + Sphinx
2. FinTech Credit Risk -- + dbt
3. Ops Control Tower -- + Airflow + Docker
4. **Supply Chain (this)** -- + Prophet + MLflow + OR-Tools + GitHub Actions CI + dbt snapshots

A reviewer who scans the four repos in order sees a complete spectrum from
quick analysis to ML / OR engineering at scale: 104 Python tests, ~100 dbt
schema tests, two singular SQL tests, a custom Airflow image, MLflow run
tracking on every Prophet fit, and CI that catches a typo in a dbt model
five seconds after the push.
