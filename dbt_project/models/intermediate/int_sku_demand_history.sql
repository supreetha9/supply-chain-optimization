{# -----------------------------------------------------------------------------
   int_sku_demand_history
   ----------------------
   Per (SKU, warehouse) demand summary over the trailing 90 days plus
   trailing 30 days. Drives days-of-supply, ABC-class adjustments, and
   reorder-point inputs for the OR-Tools optimizer.
   ----------------------------------------------------------------------------- #}
with demand as (
    select * from {{ ref('stg_demand_daily') }}
),

max_date as (
    select max(demand_date) as max_demand_date from demand
),

windowed as (
    select
        d.sku_id,
        d.warehouse_id,
        m.max_demand_date,
        sum(case when d.demand_date >  m.max_demand_date - interval '30 days' then d.units_demanded else 0 end)  as units_30d,
        sum(case when d.demand_date >  m.max_demand_date - interval '90 days' then d.units_demanded else 0 end)  as units_90d,
        sum(case when d.demand_date >  m.max_demand_date - interval '365 days' then d.units_demanded else 0 end) as units_365d,
        stddev_samp(case when d.demand_date > m.max_demand_date - interval '90 days' then d.units_demanded end)  as units_std_90d
    from demand d
    cross join max_date m
    group by d.sku_id, d.warehouse_id, m.max_demand_date
)

select
    sku_id,
    warehouse_id,
    max_demand_date,
    units_30d,
    units_90d,
    units_365d,
    cast(units_30d as double) / 30.0  as avg_daily_demand_30d,
    cast(units_90d as double) / 90.0  as avg_daily_demand_90d,
    cast(units_365d as double) / 365.0 as avg_daily_demand_365d,
    coalesce(units_std_90d, 0.0)      as units_std_90d
from windowed
