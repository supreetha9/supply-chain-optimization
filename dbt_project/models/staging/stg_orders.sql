with src as (
    select * from {{ source('raw', 'fact_orders') }}
)

select
    order_id,
    cast(order_date as timestamp)                   as order_at,
    cast(order_date as date)                        as order_date,
    sku_id,
    warehouse_id,
    customer_segment,
    cast(units_ordered as integer)                  as units_ordered,
    cast(units_fulfilled as integer)                as units_fulfilled,
    case
        when units_fulfilled = 0 then 'unfilled'
        when units_fulfilled < units_ordered then 'partial'
        else 'complete'
    end                                             as fulfillment_status
from src
