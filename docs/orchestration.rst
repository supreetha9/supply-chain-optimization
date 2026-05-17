Orchestration
=============

Airflow on Docker Compose
-------------------------

Airflow runs in a four-service Docker Compose stack:

* ``postgres`` -- Airflow metadata DB.
* ``mlflow`` -- the MLflow tracking server (sqlite backing store + local
  artifact root mounted at ``/mlruns``).
* ``airflow-init`` -- one-shot DB migration + admin user creation.
* ``airflow-scheduler`` + ``airflow-webserver`` -- the LocalExecutor pair.

The Airflow image is **custom-built** from ``airflow/Dockerfile``:

.. code-block:: docker

    FROM apache/airflow:2.10.3-python3.13

    USER root
    # Prophet's pystan/cmdstanpy backend needs a C++ toolchain on first fit.
    RUN apt-get update && apt-get install -y --no-install-recommends build-essential

    USER airflow
    RUN pip install --no-cache-dir \
            "dbt-core>=1.8,<1.10" "dbt-duckdb>=1.8,<1.10" \
            "duckdb>=1.0" "pandas>=2.2" "numpy>=2.0" "pyarrow>=16.0" \
            "scipy>=1.13" "scikit-learn>=1.5" \
            "prophet>=1.1" "mlflow>=2.16" "ortools>=9.10"

This puts ``dbt``, ``prophet``, ``mlflow``, and ``ortools`` on the worker's
``PATH`` so every ``BashOperator`` runs without venv juggling. The image is
referenced from ``docker-compose.yml`` via ``build: ./airflow`` and is
rebuilt automatically by ``make airflow-up``.

The host project root is mounted at ``/opt/airflow/repo`` so DAG tasks can
shell out to ``cd dbt_project && dbt build`` and ``python -m python.src.*``
against the same code the developer runs locally.

Environment
-----------

``docker-compose.yml`` injects ``MLFLOW_TRACKING_URI=http://mlflow:5000``
into every Airflow service. This is the value the DAG's ``forecast.py``
task reads at startup; failing fast if unset is a deliberate choice
(documented in :doc:`forecasting_methodology`).

For host-side runs, the user exports
``MLFLOW_TRACKING_URI=http://localhost:5000`` after ``make airflow-up``
brings the tracking server up. The ``.env.example`` file documents both
forms.

DAG topology
------------

``airflow/dags/supply_chain_pipeline.py`` defines a single daily DAG:

.. code-block:: text

    generate_data
        >> dbt_build_pre_forecast
        >> [forecast_demand, vendor_scoring]
    forecast_demand
        >> dbt_build_post_forecast
        >> optimize_reorder_points
        >> generate_recommendations
    [generate_recommendations, vendor_scoring] >> alert_check

The two-phase dbt build pattern
-------------------------------

The DAG runs dbt **twice** because forecasts are produced *between* dbt
invocations:

1. ``dbt_build_pre_forecast`` -- runs everything **except** models tagged
   ``needs_forecast``. These are the 8 staging views over raw parquet, the
   3 intermediate models, the 4 forecast-independent marts
   (inventory_health, otif, vendor_scorecard, warehouse_performance), and
   both snapshots. Selector:

   .. code-block:: bash

       dbt build --exclude tag:needs_forecast

2. ``forecast_demand`` -- runs Prophet, writes
   ``data/forecast/fact_demand_forecast.parquet`` (overwriting any prior
   placeholder).

3. ``dbt_build_post_forecast`` -- builds the forecast-dependent slice:
   ``stg_demand_forecast`` (now backed by real Prophet output),
   ``mart_forecast_accuracy``, and ``mart_reorder_recommendations``.
   Selector:

   .. code-block:: bash

       dbt build --select tag:needs_forecast+

The same selectors are exposed as Make targets (``make dbt-build-pre`` and
``make dbt-build-post``) for host-side iteration.

Triggering and inspecting runs
------------------------------

* ``make airflow-up`` -- start the stack (also rebuilds the custom image).
* ``make airflow-trigger`` -- run the DAG immediately.
* ``make airflow-logs`` -- tail the scheduler logs.
* ``make airflow-down`` -- stop and remove containers.

The Airflow UI is at http://localhost:8080 (``admin`` / ``admin`` from
``.env.example``); the MLflow UI is at http://localhost:5000.
