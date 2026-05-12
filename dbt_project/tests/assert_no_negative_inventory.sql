{# -----------------------------------------------------------------------------
   assert_no_negative_inventory
   ----------------------------
   Inventory snapshot integrity: on-hand and reserved units must never be
   negative, and reserved units must not exceed on-hand.
   ----------------------------------------------------------------------------- #}
select
    snapshot_date,
    sku_id,
    warehouse_id,
    on_hand_units,
    reserved_units
from {{ ref('stg_inventory_snapshot') }}
where on_hand_units  < 0
   or reserved_units < 0
   or reserved_units > on_hand_units
