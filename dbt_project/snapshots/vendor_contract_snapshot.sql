{# -----------------------------------------------------------------------------
   vendor_contract_snapshot
   ------------------------
   SCD-2 history of contract terms that drift over time:
     - contract_lead_time_days
     - lead_time_variance_days
     - payment_terms_days
     - defect_rate

   Anyone analyzing "why did our lead times shift in Q3?" can join this
   snapshot to historical purchase orders by the time window
   `dbt_valid_from <= po_date < coalesce(dbt_valid_to, po_date + 1)`.
   ----------------------------------------------------------------------------- #}
{% snapshot vendor_contract_snapshot %}
    {{
        config(
            target_schema='snapshots',
            unique_key='vendor_id',
            strategy='check',
            check_cols=[
                'contract_lead_time_days',
                'lead_time_variance_days',
                'payment_terms_days',
                'defect_rate',
            ],
        )
    }}

    select
        vendor_id,
        vendor_name,
        country,
        contract_lead_time_days,
        lead_time_variance_days,
        payment_terms_days,
        defect_rate,
        contract_start_date
    from {{ ref('stg_vendors') }}
{% endsnapshot %}
