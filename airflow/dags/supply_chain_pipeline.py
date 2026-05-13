"""Supply Chain Control Tower daily pipeline.

DAG ``supply_chain_pipeline`` orchestrates the pipeline in the order required
by the forecast-then-rebuild dbt graph:

    generate_data
        >> dbt_build_pre_forecast
        >> [forecast_demand, vendor_scoring]
    forecast_demand >> dbt_build_post_forecast >> optimize_reorder_points
        >> generate_recommendations
    [generate_recommendations, vendor_scoring] >> alert_check

Two dbt invocations are required because mart_forecast_accuracy and
mart_reorder_recommendations depend on stg_demand_forecast (tag:
needs_forecast), which is only populated AFTER forecast.py runs.

The custom ``airflow/Dockerfile`` (referenced by docker-compose.yml) ensures
dbt-core, dbt-duckdb, prophet, mlflow, and ortools are all on PATH inside
the BashOperator workers. ``MLFLOW_TRACKING_URI=http://mlflow:5000`` is
injected by docker-compose.yml so forecast.py can reach the tracking server
inside the compose network.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.operators.bash import BashOperator

from airflow import DAG

REPO_ROOT = "/opt/airflow/repo"
DBT_DIR = f"{REPO_ROOT}/dbt_project"

DEFAULT_ARGS = {
    "owner": "supply-analytics",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

DBT_ENV = f"cd {DBT_DIR} && DBT_PROFILES_DIR=. "

with DAG(
    dag_id="supply_chain_pipeline",
    description="Daily supply-chain pipeline: generate -> dbt -> Prophet -> dbt rebuild -> OR-Tools -> alerts",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["supply-chain", "dbt", "duckdb", "prophet", "mlflow", "ortools"],
) as dag:
    generate_data = BashOperator(
        task_id="generate_data",
        bash_command=f"cd {REPO_ROOT} && python -m python.src.generate_data",
    )

    dbt_build_pre_forecast = BashOperator(
        task_id="dbt_build_pre_forecast",
        bash_command=DBT_ENV + "dbt build --exclude tag:needs_forecast",
    )

    forecast_demand = BashOperator(
        task_id="forecast_demand",
        bash_command=f"cd {REPO_ROOT} && python -m python.src.forecast --top-n 50",
    )

    dbt_build_post_forecast = BashOperator(
        task_id="dbt_build_post_forecast",
        bash_command=DBT_ENV + "dbt build --select tag:needs_forecast+",
    )

    optimize_reorder_points = BashOperator(
        task_id="optimize_reorder_points",
        bash_command=f"cd {REPO_ROOT} && python -m python.src.optimization",
    )

    vendor_scoring = BashOperator(
        task_id="vendor_scoring",
        bash_command=f"cd {REPO_ROOT} && python -m python.src.vendor_scoring",
    )

    generate_recommendations = BashOperator(
        task_id="generate_recommendations",
        bash_command=(
            f"cd {REPO_ROOT} && python -m python.src.analysis --top-n 50 "
            "|| true"  # analysis re-runs forecast/opt; keep idempotent on retry
        ),
    )

    alert_check = BashOperator(
        task_id="alert_check",
        bash_command=(
            f"cd {REPO_ROOT} && python -c 'from python.src.analysis import detect_alerts, _write_alerts_log; "
            'alerts = detect_alerts(); _write_alerts_log(alerts); print(f"alerts={len(alerts)}")\''
        ),
    )

    generate_data >> dbt_build_pre_forecast
    dbt_build_pre_forecast >> [forecast_demand, vendor_scoring]
    (
        forecast_demand
        >> dbt_build_post_forecast
        >> optimize_reorder_points
        >> generate_recommendations
    )
    [generate_recommendations, vendor_scoring] >> alert_check
