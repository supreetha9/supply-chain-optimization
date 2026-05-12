{# -----------------------------------------------------------------------------
   mart_inventory_health
   ---------------------
   Per (SKU, warehouse): on-hand, available, days of supply, stockout risk
   score, slow-moving flag. Drives the Inventory Health Streamlit page.
   ----------------------------------------------------------------------------- #}
with position as (
    select * from {{ ref('int_inventory_position') }}
),
demand as (
    select * from {{ ref('int_sku_demand_history') }}
),
sku as (
    select sku_id, sku_name, category, abc_class, unit_cost, shelf_life_days
    from {{ ref('stg_skus') }}
),
warehouse as (
    select warehouse_id, warehouse_name, region from {{ ref('stg_warehouses') }}
),
service as (
    select abc_class, target_service_level
    from {{ ref('service_level_targets') }}
)

select
    p.sku_id,
    p.warehouse_id,
    sku.sku_name,
    sku.category,
    sku.abc_class,
    w.warehouse_name,
    w.region,
    p.latest_snapshot_date,
    p.on_hand_units,
    p.reserved_units,
    p.in_transit_units,
    p.available_units,
    p.inventory_position,
    coalesce(d.avg_daily_demand_30d, 0)              as avg_daily_demand_30d,
    coalesce(d.avg_daily_demand_90d, 0)              as avg_daily_demand_90d,
    {{ compute_days_of_supply('p.on_hand_units', 'd.avg_daily_demand_30d') }} as days_of_supply_30d,
    case
        when d.avg_daily_demand_30d is null or d.avg_daily_demand_30d = 0 then 1.0
        when p.on_hand_units = 0 then 1.0
        when p.on_hand_units / d.avg_daily_demand_30d < 7 then 0.85
        when p.on_hand_units / d.avg_daily_demand_30d < 14 then 0.55
        when p.on_hand_units / d.avg_daily_demand_30d < 30 then 0.20
        else 0.05
    end                                              as stockout_risk_score,
    case
        when d.units_90d is null or d.units_90d = 0 then true
        when p.on_hand_units / nullif(d.units_90d / 90.0, 0) > sku.shelf_life_days * 0.5 then true
        else false
    end                                              as is_slow_moving,
    p.on_hand_units * sku.unit_cost                  as on_hand_value_usd,
    s.target_service_level
from position p
left join demand d
    on  p.sku_id       = d.sku_id
    and p.warehouse_id = d.warehouse_id
left join sku       on sku.sku_id = p.sku_id
left join warehouse w on w.warehouse_id = p.warehouse_id
left join service   s on s.abc_class = sku.abc_class
