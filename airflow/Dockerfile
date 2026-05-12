# =============================================================================
# Custom Airflow image for supply-chain-optimization.
#
# Extends the official Airflow 2.10 / Python 3.13 image with the four data /
# ML / OR libraries the DAG's BashOperators need on PATH:
#   - dbt-core + dbt-duckdb : `cd dbt_project && dbt build` from BashOperator
#   - prophet               : forecast.py runs inside the worker
#   - mlflow                : forecast.py logs runs to the tracking server
#   - ortools               : optimization.py runs inside the worker
#
# Without this image, BashOperator tasks would shell out to a `python` that
# lacks these deps and fail at import time.
# =============================================================================

FROM apache/airflow:2.10.3-python3.13

USER root
# Prophet's pystan/cmdstanpy backends need a C++ toolchain for first-time fits.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
RUN pip install --no-cache-dir \
        "dbt-core>=1.8,<1.10" \
        "dbt-duckdb>=1.8,<1.10" \
        "duckdb>=1.0" \
        "pandas>=2.2" \
        "numpy>=2.0" \
        "pyarrow>=16.0" \
        "scipy>=1.13" \
        "scikit-learn>=1.5" \
        "prophet>=1.1" \
        "mlflow>=2.16" \
        "ortools>=9.10"
