{# -----------------------------------------------------------------------------
   mart_warehouse_performance
   --------------------------
   Per-warehouse rollup: fulfillment speed, backlog count, service-level
   attainment over the last 90 days. Drives the Warehouse Performance page.
   ----------------------------------------------------------------------------- #}
with shipments as (
    select * from {{ ref('stg_shipments') }}
),
orders as (
    select * from {{ ref('stg_orders') }}
),
warehouse as (
    select * from {{ ref('stg_warehouses') }}
),
max_dates as (
    select
        (select max(shipped_date) from shipments) as max_ship_date,
        (select max(order_date)   from orders)    as max_order_date
),
ship_recent as (
    select
        s.warehouse_id,
        avg(date_diff('day', o.order_date, s.shipped_date))    as avg_order_to_ship_days,
        avg(s.transit_days)                                    as avg_transit_days,
        sum(case when s.delivered_date <= s.promised_date then 1 else 0 end) * 1.0 / count(*)
                                                               as on_time_rate,
        count(*)                                               as shipment_count_90d,
        sum(s.units_shipped)                                   as units_shipped_90d
    from shipments s
    join orders o on o.order_id = s.order_id
    cross join max_dates m
    where s.shipped_date > m.max_ship_date - interval '90 days'
    group by s.warehouse_id
),
backlog as (
    select
        warehouse_id,
        sum(case when fulfillment_status in ('partial', 'unfilled') then 1 else 0 end) as backlog_count,
        sum(case when fulfillment_status in ('partial', 'unfilled')
                 then units_ordered - units_fulfilled else 0 end)                       as backlog_units
    from orders
    cross join max_dates m
    where order_date > m.max_order_date - interval '30 days'
    group by warehouse_id
)

select
    w.warehouse_id,
    w.warehouse_name,
    w.region,
    w.capacity_units,
    coalesce(s.shipment_count_90d, 0)         as shipment_count_90d,
    coalesce(s.units_shipped_90d, 0)          as units_shipped_90d,
    s.avg_order_to_ship_days,
    s.avg_transit_days,
    coalesce(s.on_time_rate, 0)               as on_time_rate_90d,
    coalesce(b.backlog_count, 0)              as backlog_count_30d,
    coalesce(b.backlog_units, 0)              as backlog_units_30d
from warehouse w
left join ship_recent s on s.warehouse_id = w.warehouse_id
left join backlog     b on b.warehouse_id = w.warehouse_id
