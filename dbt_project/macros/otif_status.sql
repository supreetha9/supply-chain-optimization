{# -----------------------------------------------------------------------------
   otif_status
   -----------
   Classifies a shipment as OTIF (on-time + in-full), late, short, or both.
   Inputs:
     promised_date_col   -- date the customer was told to expect
     delivered_date_col  -- date the shipment actually arrived
     units_ordered_col   -- units the customer asked for
     units_shipped_col   -- units actually shipped
   Output: one of 'on_time_in_full', 'late_only', 'short_only', 'late_and_short'.
   ----------------------------------------------------------------------------- #}
{% macro otif_status(promised_date_col, delivered_date_col, units_ordered_col, units_shipped_col) %}
    case
        when {{ delivered_date_col }} <= {{ promised_date_col }}
             and {{ units_shipped_col }} >= {{ units_ordered_col }}
            then 'on_time_in_full'
        when {{ delivered_date_col }} > {{ promised_date_col }}
             and {{ units_shipped_col }} >= {{ units_ordered_col }}
            then 'late_only'
        when {{ delivered_date_col }} <= {{ promised_date_col }}
             and {{ units_shipped_col }} < {{ units_ordered_col }}
            then 'short_only'
        else 'late_and_short'
    end
{% endmacro %}
