{# -----------------------------------------------------------------------------
   int_inventory_position
   ----------------------
   Latest snapshot per (SKU, warehouse) joined with open POs that haven't yet
   arrived. inventory_position = on_hand + in_transit + open_po - reserved.

   This is the key driver of mart_reorder_recommendations: we trigger a
   reorder when inventory_position drops below the reorder_point that
   OR-Tools' optimizer chose.
   ----------------------------------------------------------------------------- #}
with snapshots as (
    select * from {{ ref('stg_inventory_snapshot') }}
),

latest_per_pair as (
    select
        sku_id,
        warehouse_id,
        max(snapshot_date) as latest_snapshot_date
    from snapshots
    group by sku_id, warehouse_id
),

latest as (
    select s.*
    from snapshots s
    inner join latest_per_pair l
        on  s.sku_id        = l.sku_id
        and s.warehouse_id  = l.warehouse_id
        and s.snapshot_date = l.latest_snapshot_date
),

open_pos as (
    select
        sku_id,
        warehouse_id,
        sum(units_ordered) as open_po_units
    from {{ ref('stg_purchase_orders') }}
    where actual_arrival_date >= current_date
    group by sku_id, warehouse_id
)

select
    l.sku_id,
    l.warehouse_id,
    l.snapshot_date            as latest_snapshot_date,
    l.on_hand_units,
    l.reserved_units,
    l.in_transit_units,
    l.available_units,
    coalesce(p.open_po_units, 0) as open_po_units,
    l.on_hand_units + l.in_transit_units + coalesce(p.open_po_units, 0) - l.reserved_units
                                                       as inventory_position
from latest l
left join open_pos p
    on  l.sku_id       = p.sku_id
    and l.warehouse_id = p.warehouse_id
