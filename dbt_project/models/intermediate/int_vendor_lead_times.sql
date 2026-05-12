{# -----------------------------------------------------------------------------
   int_vendor_lead_times
   ---------------------
   Vendor performance rollups derived from purchase-order arrivals over the
   last 365 days. Feeds vendor scorecard + safety-stock formula.
   ----------------------------------------------------------------------------- #}
with pos as (
    select * from {{ ref('stg_purchase_orders') }}
),

max_date as (
    select max(po_date) as max_po_date from pos
),

windowed as (
    select
        p.vendor_id,
        count(*)                                                                      as po_count_365d,
        avg(date_diff('day', p.po_date, p.actual_arrival_date))                       as actual_lead_time_avg,
        stddev_samp(date_diff('day', p.po_date, p.actual_arrival_date))               as actual_lead_time_std,
        avg(p.arrival_offset_days)                                                    as arrival_offset_avg,
        stddev_samp(p.arrival_offset_days)                                            as arrival_offset_std,
        sum(case when p.arrival_status = 'late' then 1 else 0 end)                    as late_arrivals_count,
        sum(case when p.arrival_status = 'late' then 1 else 0 end) * 1.0 / count(*)   as late_arrival_rate,
        sum(p.units_ordered)                                                          as units_ordered_365d
    from pos p
    cross join max_date m
    where p.po_date > m.max_po_date - interval '365 days'
    group by p.vendor_id
)

select
    w.vendor_id,
    v.contract_lead_time_days,
    v.lead_time_variance_days,
    v.defect_rate,
    coalesce(w.po_count_365d, 0)            as po_count_365d,
    w.actual_lead_time_avg,
    w.actual_lead_time_std,
    w.arrival_offset_avg,
    w.arrival_offset_std,
    coalesce(w.late_arrivals_count, 0)      as late_arrivals_count,
    coalesce(w.late_arrival_rate, 0.0)      as late_arrival_rate,
    coalesce(w.units_ordered_365d, 0)       as units_ordered_365d
from {{ ref('stg_vendors') }} v
left join windowed w on w.vendor_id = v.vendor_id
