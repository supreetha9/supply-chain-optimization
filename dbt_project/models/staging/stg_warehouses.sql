with src as (
    select * from {{ source('raw', 'dim_warehouses') }}
)

select
    warehouse_id,
    warehouse_name,
    region,
    cast(capacity_units as integer)                 as capacity_units,
    cast(location_lat as double)                    as location_lat,
    cast(location_lon as double)                    as location_lon
from src
