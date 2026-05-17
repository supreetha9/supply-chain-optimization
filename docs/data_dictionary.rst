Data Dictionary
===============

This page enumerates every table the platform produces or consumes -- raw
parquet sources, the runtime forecast artifact, dbt staging / intermediate /
mart models, and SCD-2 snapshots.

Raw ERP parquet tables (``data/raw/``)
--------------------------------------

Generated deterministically by ``python/src/generate_data.py``.

``dim_skus`` (500 rows)
~~~~~~~~~~~~~~~~~~~~~~~~

* ``sku_id`` (PK)
* ``sku_name``
* ``category`` -- electronics / apparel / home_goods / grocery / toys
* ``subcategory``
* ``unit_cost`` (USD)
* ``selling_price`` (USD)
* ``storage_cost_per_unit_per_day`` (USD)
* ``shelf_life_days``
* ``seasonality_flag`` (bool) -- drives weekly + holiday demand swings
* ``abc_class`` -- A / B / C, drives default service level
* ``primary_vendor_id`` -> dim_vendors

``dim_vendors`` (20 rows)
~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``vendor_id`` (PK)
* ``vendor_name``
* ``country`` -- China / USA / Vietnam / Mexico / India
* ``contract_lead_time_days`` -- 5..45
* ``lead_time_variance_days`` -- correlated with contract_lead_time
* ``payment_terms_days`` -- 15 / 30 / 45 / 60 / 90
* ``defect_rate`` -- Beta(2, 60) clipped to [0.001, 0.10]
* ``contract_start_date``

``dim_warehouses`` (5 rows)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``warehouse_id`` (PK)
* ``warehouse_name``
* ``region`` -- West / Central / East / South / International
* ``capacity_units``
* ``location_lat``, ``location_lon``

``fact_demand_daily`` (~1.1M rows)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``demand_date``, ``sku_id``, ``warehouse_id``, ``units_demanded``

``fact_orders`` (30K rows)
~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``order_id`` (PK), ``order_date``, ``sku_id``, ``warehouse_id``,
  ``customer_segment``, ``units_ordered``, ``units_fulfilled``

``fact_inventory_snapshot`` (~150K rows, weekly)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``snapshot_date``, ``sku_id``, ``warehouse_id``, ``on_hand_units``,
  ``reserved_units``, ``in_transit_units``

``fact_purchase_orders`` (4K rows)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``po_id`` (PK), ``po_date``, ``vendor_id``, ``sku_id``, ``warehouse_id``,
  ``units_ordered``, ``expected_arrival_date``, ``actual_arrival_date``,
  ``unit_cost_at_po``

``fact_shipments`` (~30K rows)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``shipment_id`` (PK), ``order_id``, ``sku_id``, ``warehouse_id``,
  ``promised_date``, ``shipped_date``, ``delivered_date``, ``units_shipped``


Runtime forecast artifact (``data/forecast/``)
----------------------------------------------

``fact_demand_forecast.parquet``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Written by ``python/src/forecast.py`` (Prophet) and re-read into dbt via
``stg_demand_forecast``. Overwritten on every forecast run.

* ``forecast_date``, ``sku_id``, ``warehouse_id``
* ``yhat`` -- point forecast (units)
* ``yhat_lower``, ``yhat_upper`` -- 80% confidence band
* ``model_run_id`` -- 12-char hex tying every row in this run to its
  parent MLflow run

``reorder_recommendations.parquet``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Written by ``python/src/optimization.py`` (OR-Tools).

* ``sku_id``, ``warehouse_id``
* ``reorder_point_optimized`` -- OR-Tools choice
* ``reorder_point_textbook`` -- benchmark from textbook formula
* ``expected_holding_cost``, ``expected_stockout_cost``,
  ``expected_total_cost`` (USD over the lead-time window)
* ``cost_savings_vs_textbook`` (USD)

``vendor_scores.parquet``
~~~~~~~~~~~~~~~~~~~~~~~~~

Written by ``python/src/vendor_scoring.py``.

* ``vendor_id``, ``vendor_name``, ``rank`` (1 = best)
* ``composite_score`` -- 0-100, lower = better
* Component sub-scores: ``score_lead_time_overshoot``, ``score_late_arrival``,
  ``score_defect``, ``score_variance``


dbt models
----------

Staging (9 models, all materialized as views)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``stg_skus``, ``stg_vendors``, ``stg_warehouses``
* ``stg_demand_daily``
* ``stg_orders`` -- adds derived ``fulfillment_status``
* ``stg_inventory_snapshot`` -- adds derived ``available_units``
* ``stg_purchase_orders`` -- adds ``arrival_offset_days``, ``arrival_status``
* ``stg_shipments`` -- adds ``transit_days``, ``delivery_offset_days``
* ``stg_demand_forecast`` -- *tagged ``needs_forecast``;* surfaces the
  Prophet output parquet into the dbt graph

Intermediate (3 models, ephemeral)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``int_sku_demand_history`` -- 30 / 90 / 365-day rolling demand stats
* ``int_vendor_lead_times`` -- vendor-level lead time + late-rate rollups
* ``int_inventory_position`` -- on-hand + in-transit + open POs - reserved

Marts (6 models, materialized as tables)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``mart_inventory_health``
* ``mart_otif``
* ``mart_vendor_scorecard``
* ``mart_warehouse_performance``
* ``mart_forecast_accuracy`` (tagged ``needs_forecast``)
* ``mart_reorder_recommendations`` (tagged ``needs_forecast``)

Snapshots (SCD-2, 2 models)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``vendor_contract_snapshot`` -- tracks ``contract_lead_time_days``,
  ``lead_time_variance_days``, ``payment_terms_days``, ``defect_rate``
* ``sku_pricing_snapshot`` -- tracks ``unit_cost``, ``selling_price``,
  ``storage_cost_per_unit_per_day``


Seeds
-----

* ``service_level_targets`` -- per-ABC class default service level + stockout
  penalty (A: 0.98 / B: 0.95 / C: 0.90).
* ``stockout_cost_overrides`` -- per-SKU penalty overrides (e.g.
  perishables priced above the default).
