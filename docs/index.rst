Supply Chain Control Tower
==========================

End-to-end supply-chain analytics platform that demonstrates the full
analytics-engineering -> ML -> operations-research -> DevOps spectrum:

* **dbt** transforms 8 ERP-style parquet sources into 9 staging views, 3
  intermediate models, 6 marts, and 2 SCD-2 snapshots in a local DuckDB
  warehouse.
* **Prophet** forecasts SKU x warehouse demand 30 days ahead and logs every
  fit to a dedicated **MLflow** tracking server.
* **Google OR-Tools** picks cost-minimizing reorder points subject to a
  per-ABC service-level floor, benchmarked against a textbook safety-stock
  formula.
* **Airflow** (Docker Compose) orchestrates the daily pipeline.
* A 6-page **Streamlit** dashboard surfaces every KPI and lets the user
  toggle the optimizer-vs-textbook reorder comparison.
* **GitHub Actions** lints, tests, and validates dbt parse on every push.

Useful links:

* `MLflow tracking UI <http://localhost:5000>`_ (after ``make airflow-up``)
* `Airflow webserver <http://localhost:8080>`_ (admin / admin)
* `Streamlit dashboard <http://localhost:8501>`_ (after ``make app``)
* `README on GitHub <https://github.com/your-org/supply-chain-optimization>`_

.. toctree::
   :maxdepth: 2
   :caption: Reference

   business_problem
   data_dictionary
   metric_dictionary
   forecasting_methodology
   optimization_methodology
   orchestration
   cicd
   executive_summary
