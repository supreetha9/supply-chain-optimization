with src as (
    select * from {{ source('raw', 'dim_skus') }}
)

select
    sku_id,
    sku_name,
    category,
    subcategory,
    cast(unit_cost as double)                       as unit_cost,
    cast(selling_price as double)                   as selling_price,
    cast(storage_cost_per_unit_per_day as double)   as storage_cost_per_unit_per_day,
    cast(shelf_life_days as integer)                as shelf_life_days,
    cast(seasonality_flag as boolean)               as is_seasonal,
    abc_class,
    primary_vendor_id
from src
