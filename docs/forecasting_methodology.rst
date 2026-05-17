Forecasting Methodology
=======================

Implemented in ``python/src/forecast.py``. Each (SKU, warehouse) pair gets
its own Prophet model, fit and tracked independently in MLflow.

Model architecture
------------------

`Prophet <https://facebook.github.io/prophet/>`_ is a decomposable
additive (or multiplicative) time-series model:

.. code-block:: text

    y(t) = trend(t) + seasonality(t) + holidays(t) + epsilon

We use:

* **trend** -- piecewise linear with automatic changepoint detection.
* **weekly seasonality** -- enabled for every series (Fourier order = 3).
* **yearly seasonality** -- enabled for SKUs flagged ``is_seasonal``.
* **daily seasonality** -- disabled (we have daily granularity, not
  intra-day).
* **holidays** -- US country holidays via ``Prophet.add_country_holidays``,
  which captures the Black Friday / end-of-quarter spikes the data
  generator bakes in.
* **changepoint_prior_scale** -- 0.05 (Prophet default; adapts to demand
  shifts without overfitting).
* **seasonality_mode** -- ``multiplicative`` for seasonal SKUs (peaks scale
  with the trend), ``additive`` otherwise.

Training and holdout
--------------------

For each series we hold out the last 30 days for in-sample evaluation:

* MAPE -- mean absolute percentage error (rows with actual > 0).
* WAPE -- sum-based percentage error.
* mean_bias -- signed forecast error.

The forward-looking 30-day horizon (the part we actually persist) is
predicted *after* the holdout slice and never overlaps it.

MLflow workflow
---------------

Tracking URI contract
~~~~~~~~~~~~~~~~~~~~~

``forecast.py`` reads ``MLFLOW_TRACKING_URI`` from the environment at module
import. **It fails fast with a clear error if the variable is unset** -- no
silent fallback to a local file store. This guarantees a hiring manager
demoing the project sees one of two valid configurations:

* ``MLFLOW_TRACKING_URI=http://localhost:5000`` (host shell, after
  ``make airflow-up``)
* ``MLFLOW_TRACKING_URI=http://mlflow:5000`` (inside Airflow's docker
  network -- the value docker-compose injects for DAG tasks)

Run hierarchy
~~~~~~~~~~~~~

A batch run creates one **parent run** named ``batch_<model_run_id>`` whose
parameters describe the batch (``series_count``, ``horizon_days``,
``holdout_days``, ``top_n``). Inside that, every (SKU, warehouse) fit is a
**nested run** named ``<sku_id>_<warehouse_id>`` with:

* **Params:** ``seasonality_mode``, ``changepoint_prior_scale``,
  ``weekly_seasonality``, ``yearly_seasonality``.
* **Metrics:** ``mape``, ``wape``, ``mean_bias``, ``observation_count``.
* **Tags:** ``sku_id``, ``warehouse_id``, ``abc_class``,
  ``model_run_id``, and ``airflow_run_id`` if the run was triggered from
  the DAG.

Persistence
~~~~~~~~~~~

The combined forecast for every series is concatenated and written to
``data/forecast/fact_demand_forecast.parquet`` with columns
``forecast_date, sku_id, warehouse_id, yhat, yhat_lower, yhat_upper,
model_run_id``. The ``stg_demand_forecast`` dbt model surfaces this back
into the warehouse for ``mart_forecast_accuracy`` and
``mart_reorder_recommendations``.

Why MLflow matters here
-----------------------

At ~1500 (SKU, warehouse) pairs (or even the default top-50 subset), you
need a way to:

1. Find which models are degrading -- *"show me runs from the last week
   where MAPE > 30%"*.
2. Compare an experiment with new seasonality settings against last week's
   baseline -- the parent ``batch`` run is the unit of comparison.
3. Reproduce any production forecast: every row in the forecast parquet
   carries a ``model_run_id`` that maps 1:1 to the parent MLflow run.

Operational tips
----------------

* The first Prophet fit per process triggers a ``cmdstanpy`` C++ compile
  that takes ~30s. Subsequent fits in the same process reuse the compiled
  model.
* Default ``--top-n 50`` keeps the host-side run under 5 minutes. Pass
  ``--all`` for the full batch (~30 minutes).
