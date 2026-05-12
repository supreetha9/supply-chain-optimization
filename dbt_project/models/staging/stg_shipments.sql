with src as (
    select * from {{ source('raw', 'fact_shipments') }}
)

select
    shipment_id,
    order_id,
    sku_id,
    warehouse_id,
    cast(promised_date as date)                     as promised_date,
    cast(shipped_date as date)                      as shipped_date,
    cast(delivered_date as date)                    as delivered_date,
    cast(units_shipped as integer)                  as units_shipped,
    date_diff('day', cast(shipped_date as date), cast(delivered_date as date))   as transit_days,
    date_diff('day', cast(promised_date as date), cast(delivered_date as date))  as delivery_offset_days
from src
