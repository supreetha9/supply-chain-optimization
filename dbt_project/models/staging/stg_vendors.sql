with src as (
    select * from {{ source('raw', 'dim_vendors') }}
)

select
    vendor_id,
    vendor_name,
    country,
    cast(contract_lead_time_days as integer)        as contract_lead_time_days,
    cast(lead_time_variance_days as double)         as lead_time_variance_days,
    cast(payment_terms_days as integer)             as payment_terms_days,
    cast(defect_rate as double)                     as defect_rate,
    cast(contract_start_date as date)               as contract_start_date
from src
