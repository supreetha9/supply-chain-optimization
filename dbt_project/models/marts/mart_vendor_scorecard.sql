{# -----------------------------------------------------------------------------
   mart_vendor_scorecard
   ---------------------
   Per-vendor: avg lead time, lead-time variance, late shipment rate, defect
   rate, total cost impact (price * units * defect penalty). Composite score
   is a weighted blend (lower = better).
   ----------------------------------------------------------------------------- #}
with vendor as (
    select * from {{ ref('stg_vendors') }}
),
lt as (
    select * from {{ ref('int_vendor_lead_times') }}
),
po_cost as (
    select
        vendor_id,
        sum(units_ordered * unit_cost_at_po) as total_po_cost_365d
    from {{ ref('stg_purchase_orders') }}
    where po_date > (select max(po_date) - interval '365 days' from {{ ref('stg_purchase_orders') }})
    group by vendor_id
)

select
    v.vendor_id,
    v.vendor_name,
    v.country,
    v.contract_lead_time_days,
    lt.actual_lead_time_avg,
    lt.actual_lead_time_std,
    lt.late_arrival_rate,
    v.defect_rate,
    coalesce(pc.total_po_cost_365d, 0)                       as total_po_cost_365d,
    coalesce(pc.total_po_cost_365d, 0) * v.defect_rate       as defect_cost_impact_usd,
    /*  Composite score 0-100, lower = better.
        Components (each weighted, sum to 100 worst-case):
          lead_time_overshoot pct  -> up to 30 pts
          late_arrival_rate * 100  -> up to 30 pts
          defect_rate * 1000       -> up to 30 pts (capped)
          variance ratio           -> up to 10 pts (capped)
    */
    least(100,
          coalesce(greatest(0, (lt.actual_lead_time_avg - v.contract_lead_time_days)
                / nullif(v.contract_lead_time_days, 0)) * 100, 0) * 0.30
        + coalesce(lt.late_arrival_rate, 0) * 100 * 0.30
        + least(v.defect_rate * 1000, 30)
        + least(coalesce(lt.actual_lead_time_std, 0) / nullif(v.contract_lead_time_days, 0) * 100, 10)
    )                                                        as composite_score
from vendor v
left join lt        on lt.vendor_id = v.vendor_id
left join po_cost pc on pc.vendor_id = v.vendor_id
