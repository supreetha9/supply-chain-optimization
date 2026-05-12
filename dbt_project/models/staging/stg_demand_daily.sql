with src as (
    select * from {{ source('raw', 'fact_demand_daily') }}
)

select
    cast(demand_date as date)                       as demand_date,
    sku_id,
    warehouse_id,
    cast(units_demanded as integer)                 as units_demanded
from src
