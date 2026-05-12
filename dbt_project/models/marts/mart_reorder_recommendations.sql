{# -----------------------------------------------------------------------------
   mart_reorder_recommendations
   ----------------------------
   Joins live inventory position with the Prophet forecast (next 30 days) and
   surfaces a row per (SKU, warehouse) where inventory_position will fall
   below the safety stock during the forecast horizon. Final reorder_point
   is filled in by python/src/optimization.py — this mart shows the
   pre-optimization signal so the dashboard can render before optimize runs.

   Tagged needs_forecast.
   ----------------------------------------------------------------------------- #}
with position as (
    select * from {{ ref('int_inventory_position') }}
),
demand as (
    select * from {{ ref('int_sku_demand_history') }}
),
forecast as (
    select
        sku_id,
        warehouse_id,
        sum(forecast_units) as forecast_units_30d
    from {{ ref('stg_demand_forecast') }}
    where forecast_date <= (select max(forecast_date) from {{ ref('stg_demand_forecast') }})
      and forecast_date >  (select max(forecast_date) - interval '30 days' from {{ ref('stg_demand_forecast') }})
    group by sku_id, warehouse_id
),
sku as (
    select sku_id, sku_name, category, abc_class, unit_cost, primary_vendor_id
    from {{ ref('stg_skus') }}
),
vendor as (
    select vendor_id, contract_lead_time_days, lead_time_variance_days
    from {{ ref('stg_vendors') }}
),
service as (
    select * from {{ ref('service_level_targets') }}
)

select
    p.sku_id,
    p.warehouse_id,
    sku.sku_name,
    sku.category,
    sku.abc_class,
    sku.unit_cost,
    sku.primary_vendor_id,
    v.contract_lead_time_days,
    v.lead_time_variance_days,
    s.target_service_level,
    p.inventory_position,
    coalesce(d.avg_daily_demand_30d, 0)              as avg_daily_demand_30d,
    coalesce(d.units_std_90d, 0)                     as units_std_90d,
    coalesce(f.forecast_units_30d, 0)                as forecast_units_30d,
    /*  Textbook safety stock = Z * sqrt(lead_time) * std_demand.
        Z=1.65 ~ 95% service level for ABC=B; we let optimization.py refine.  */
    1.65 * sqrt(coalesce(v.contract_lead_time_days, 14)) * coalesce(d.units_std_90d, 0)
                                                     as safety_stock_baseline,
    /*  pre-optimization reorder hint: avg daily demand x lead time + safety stock  */
    coalesce(d.avg_daily_demand_30d, 0) * coalesce(v.contract_lead_time_days, 14)
        + 1.65 * sqrt(coalesce(v.contract_lead_time_days, 14)) * coalesce(d.units_std_90d, 0)
                                                     as reorder_point_baseline,
    case
        when p.inventory_position
             <  coalesce(d.avg_daily_demand_30d, 0) * coalesce(v.contract_lead_time_days, 14)
              + 1.65 * sqrt(coalesce(v.contract_lead_time_days, 14)) * coalesce(d.units_std_90d, 0)
            then true
        else false
    end                                              as needs_reorder
from position p
left join demand   d on d.sku_id = p.sku_id and d.warehouse_id = p.warehouse_id
left join forecast f on f.sku_id = p.sku_id and f.warehouse_id = p.warehouse_id
left join sku       on sku.sku_id = p.sku_id
left join vendor   v on v.vendor_id = sku.primary_vendor_id
left join service  s on s.abc_class = sku.abc_class
