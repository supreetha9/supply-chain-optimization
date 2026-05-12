{# -----------------------------------------------------------------------------
   mart_otif
   ---------
   On-Time-In-Full attainment by warehouse, SKU category, and month. OTIF =
   shipments delivered on-or-before promised_date AND units_shipped >=
   units_ordered (across the joined order line).
   ----------------------------------------------------------------------------- #}
with shipments as (
    select * from {{ ref('stg_shipments') }}
),
orders as (
    select order_id, units_ordered from {{ ref('stg_orders') }}
),
sku as (
    select sku_id, category from {{ ref('stg_skus') }}
),
warehouse as (
    select warehouse_id, warehouse_name, region from {{ ref('stg_warehouses') }}
),
joined as (
    select
        s.shipment_id,
        s.warehouse_id,
        s.sku_id,
        date_trunc('month', s.shipped_date)::date    as ship_month,
        s.units_shipped,
        coalesce(o.units_ordered, s.units_shipped)   as units_ordered,
        s.promised_date,
        s.delivered_date,
        {{ otif_status('s.promised_date', 's.delivered_date',
                       'coalesce(o.units_ordered, s.units_shipped)', 's.units_shipped') }} as otif_status
    from shipments s
    left join orders o on o.order_id = s.order_id
)

select
    j.warehouse_id,
    w.warehouse_name,
    w.region,
    sk.category,
    j.ship_month,
    count(*)                                                                 as shipment_count,
    sum(case when j.otif_status = 'on_time_in_full' then 1 else 0 end)       as otif_count,
    sum(case when j.otif_status = 'late_only' then 1 else 0 end)             as late_only_count,
    sum(case when j.otif_status = 'short_only' then 1 else 0 end)            as short_only_count,
    sum(case when j.otif_status = 'late_and_short' then 1 else 0 end)        as late_and_short_count,
    sum(case when j.otif_status = 'on_time_in_full' then 1 else 0 end) * 1.0 / count(*)  as otif_rate,
    sum(j.units_shipped) * 1.0 / nullif(sum(j.units_ordered), 0)             as fill_rate
from joined j
left join warehouse w on w.warehouse_id = j.warehouse_id
left join sku sk on sk.sku_id = j.sku_id
group by j.warehouse_id, w.warehouse_name, w.region, sk.category, j.ship_month
