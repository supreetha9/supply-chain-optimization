Metric Dictionary
=================

Every KPI surfaced in the dashboard, with formula and business meaning.

Service-level metrics
---------------------

OTIF (On-Time-In-Full)
~~~~~~~~~~~~~~~~~~~~~~

* **Formula:** ``count(shipments where delivered_date <= promised_date AND units_shipped >= units_ordered) / count(shipments)``
* **Range:** [0, 1]; industry benchmarks 0.92-0.98 for B2C, 0.85-0.95 for B2B.
* **Computed in:** ``mart_otif``, sliced by warehouse x SKU category x month.

Fill Rate
~~~~~~~~~

* **Formula:** ``sum(units_shipped) / sum(units_ordered)``
* **Range:** [0, 1]. A pure quantity metric -- a 7-day-late shipment of all
  the units still scores 1.0 here (use OTIF for the strict version).
* **Computed in:** ``mart_otif`` and the executive overview.

Inventory metrics
-----------------

Days of Supply
~~~~~~~~~~~~~~

* **Formula:** ``on_hand_units / avg_daily_demand_30d`` (capped at 999 when
  demand is near zero).
* **Range:** [0, 999]; healthy values 14-60.
* **Computed in:** ``mart_inventory_health`` via the ``compute_days_of_supply``
  macro.

Stockout Risk Score
~~~~~~~~~~~~~~~~~~~

* **Formula:** Piecewise function of days-of-supply: 1.0 if no demand history
  or zero on-hand; 0.85 if days_of_supply < 7; 0.55 if < 14; 0.20 if < 30;
  0.05 otherwise.
* **Range:** [0, 1]; values >= 0.85 trigger an "imminent stockout" alert.
* **Computed in:** ``mart_inventory_health``.

Inventory Turnover (annualized)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Formula:** ``units_demanded_365d / mean(on_hand_units)``
* **Range:** Healthy 6-12x for fast movers, 2-4x for slow movers.

On-Hand Value (USD)
~~~~~~~~~~~~~~~~~~~

* **Formula:** ``on_hand_units * unit_cost`` summed over a rollup dimension.
* **Computed in:** ``mart_inventory_health``.

Forecast accuracy metrics
-------------------------

MAPE (Mean Absolute Percentage Error)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Formula:** ``mean(|forecast - actual| / actual)`` over rows with actual > 0.
* **Range:** [0, ∞); 0.10-0.25 is typical for retail SKUs.
* **Limitation:** Heavily distorted by small-actual rows; use WAPE alongside.

WAPE (Weighted Absolute Percentage Error)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Formula:** ``sum(|forecast - actual|) / sum(actual)``
* **Better than MAPE** when actuals span multiple orders of magnitude.

Bias (Mean Forecast Error)
~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Formula:** ``mean(forecast - actual)``
* **Range:** Real numbers; positive = systematic over-forecast, negative =
  under-forecast. Watch for trend changes month-over-month.

Coverage 95
~~~~~~~~~~~

* **Formula:** ``count(actual within [yhat_lower, yhat_upper]) / count(rows)``
* **Range:** [0, 1]; a well-calibrated forecast should land at ~0.95.

Vendor metrics
--------------

Composite Vendor Score (0-100, lower = better)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Weighted blend of four normalized 0-100 components:

* Lead-time overshoot:    weight 0.30
* Late-arrival rate:      weight 0.30
* Defect rate (* 1000):   weight 0.30
* Variance ratio:         weight 0.10

Implemented in ``python/src/vendor_scoring.py`` and ``mart_vendor_scorecard``.

Late Arrival Rate
~~~~~~~~~~~~~~~~~

* **Formula:** ``count(POs where actual_arrival_date > expected_arrival_date) / count(POs)``
* Computed over the trailing 365 days in ``int_vendor_lead_times``.

Replenishment metrics
---------------------

Reorder Point (textbook)
~~~~~~~~~~~~~~~~~~~~~~~~

* **Formula:** ``avg_daily_demand * lead_time_days + z * sqrt(lead_time_days) * std_daily_demand``
* z corresponds to a target service level (default 0.99 in the textbook
  benchmark).
* Implemented in ``python/src/safety_stock.py``.

Reorder Point (OR-Tools optimized)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* The R that minimizes
  ``expected_holding_cost(R) + expected_stockout_cost(R)`` subject to
  ``service_level >= target`` and ``R <= capacity / 2``.
* Solved by GLOP over a convex candidate grid in
  ``python/src/optimization.py``.

Cost Savings vs Textbook
~~~~~~~~~~~~~~~~~~~~~~~~

* **Formula:** ``expected_total_cost(textbook_R) - expected_total_cost(optimized_R)``
* Reported per (SKU, warehouse) in ``reorder_recommendations.parquet`` and
  aggregated on the Replenishment dashboard page.
