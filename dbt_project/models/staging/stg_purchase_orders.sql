with src as (
    select * from {{ source('raw', 'fact_purchase_orders') }}
)

select
    po_id,
    cast(po_date as date)                           as po_date,
    vendor_id,
    sku_id,
    warehouse_id,
    cast(units_ordered as integer)                  as units_ordered,
    cast(expected_arrival_date as date)             as expected_arrival_date,
    cast(actual_arrival_date as date)               as actual_arrival_date,
    date_diff('day', cast(expected_arrival_date as date), cast(actual_arrival_date as date)) as arrival_offset_days,
    case
        when actual_arrival_date <= expected_arrival_date then 'on_time'
        else 'late'
    end                                             as arrival_status,
    cast(unit_cost_at_po as double)                 as unit_cost_at_po
from src
