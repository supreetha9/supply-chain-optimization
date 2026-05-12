{# -----------------------------------------------------------------------------
   sku_pricing_snapshot
   --------------------
   SCD-2 history of SKU pricing/cost so margin and inventory-value analyses
   can be done as-of a historical date.

   Tracked columns:
     - unit_cost
     - selling_price
     - storage_cost_per_unit_per_day
   ----------------------------------------------------------------------------- #}
{% snapshot sku_pricing_snapshot %}
    {{
        config(
            target_schema='snapshots',
            unique_key='sku_id',
            strategy='check',
            check_cols=[
                'unit_cost',
                'selling_price',
                'storage_cost_per_unit_per_day',
            ],
        )
    }}

    select
        sku_id,
        sku_name,
        category,
        subcategory,
        unit_cost,
        selling_price,
        storage_cost_per_unit_per_day,
        abc_class
    from {{ ref('stg_skus') }}
{% endsnapshot %}
