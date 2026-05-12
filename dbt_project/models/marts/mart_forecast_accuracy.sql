{# -----------------------------------------------------------------------------
   mart_forecast_accuracy
   ----------------------
   Joins Prophet forecast (stg_demand_forecast) to actuals (stg_demand_daily)
   on (sku_id, warehouse_id, date) and computes rolling MAPE / WAPE / bias
   per SKU.

   Tagged needs_forecast so the Airflow DAG only refreshes this after
   forecast.py has produced data/forecast/fact_demand_forecast.parquet.
   ----------------------------------------------------------------------------- #}
with forecast as (
    select * from {{ ref('stg_demand_forecast') }}
),
actuals as (
    select * from {{ ref('stg_demand_daily') }}
),
sku as (
    select sku_id, sku_name, category, abc_class from {{ ref('stg_skus') }}
),
joined as (
    select
        f.sku_id,
        f.warehouse_id,
        f.forecast_date,
        f.forecast_units,
        f.forecast_units_lower,
        f.forecast_units_upper,
        a.units_demanded                            as actual_units,
        f.model_run_id,
        abs(f.forecast_units - a.units_demanded)    as abs_error,
        f.forecast_units - a.units_demanded         as bias,
        case
            when a.units_demanded > 0 then abs(f.forecast_units - a.units_demanded) / a.units_demanded
            else null
        end                                         as ape
    from forecast f
    inner join actuals a
        on  a.sku_id       = f.sku_id
        and a.warehouse_id = f.warehouse_id
        and a.demand_date  = f.forecast_date
)

select
    j.sku_id,
    j.warehouse_id,
    s.sku_name,
    s.category,
    s.abc_class,
    count(*)                                                          as observation_count,
    avg(j.ape)                                                        as mape,
    sum(j.abs_error) * 1.0 / nullif(sum(j.actual_units), 0)           as wape,
    avg(j.bias)                                                       as mean_bias,
    sum(case when j.actual_units between j.forecast_units_lower
                                    and j.forecast_units_upper
             then 1 else 0 end) * 1.0 / count(*)                      as coverage_95,
    max(j.model_run_id)                                               as latest_model_run_id
from joined j
left join sku s on s.sku_id = j.sku_id
group by j.sku_id, j.warehouse_id, s.sku_name, s.category, s.abc_class
