{# -----------------------------------------------------------------------------
   assert_po_arrival_after_order
   -----------------------------
   Every purchase order must have its expected_arrival_date strictly after
   po_date. (Actual arrival can be earlier than expected -- that's just an
   on-time PO -- but the contracted arrival date should never be before the
   order was placed.)
   ----------------------------------------------------------------------------- #}
select
    po_id,
    po_date,
    expected_arrival_date,
    actual_arrival_date
from {{ ref('stg_purchase_orders') }}
where expected_arrival_date <= po_date
