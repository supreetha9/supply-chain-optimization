with src as (
    select * from {{ source('raw', 'fact_inventory_snapshot') }}
)

select
    cast(snapshot_date as date)                     as snapshot_date,
    sku_id,
    warehouse_id,
    cast(on_hand_units as integer)                  as on_hand_units,
    cast(reserved_units as integer)                 as reserved_units,
    cast(in_transit_units as integer)               as in_transit_units,
    cast(on_hand_units - reserved_units as integer) as available_units
from src
