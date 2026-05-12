{# -----------------------------------------------------------------------------
   stg_demand_forecast
   -------------------
   Surfaces the runtime forecast artifact produced by python/src/forecast.py
   (Prophet) into the dbt graph. The parquet file is overwritten on every
   forecast run; mart_forecast_accuracy and mart_reorder_recommendations
   depend on this view via the `needs_forecast` tag.

   If the forecast hasn't run yet, this model returns 0 rows but still
   compiles (empty parquet UNION'd with the schema definition). Tagged
   `needs_forecast` so the Airflow DAG can isolate it in dbt_build_post_forecast.
   ----------------------------------------------------------------------------- #}
with src as (
    select * from {{ source('forecast', 'fact_demand_forecast') }}
)

select
    cast(forecast_date as date)                     as forecast_date,
    sku_id,
    warehouse_id,
    cast(yhat as double)                            as forecast_units,
    cast(yhat_lower as double)                      as forecast_units_lower,
    cast(yhat_upper as double)                      as forecast_units_upper,
    model_run_id
from src
