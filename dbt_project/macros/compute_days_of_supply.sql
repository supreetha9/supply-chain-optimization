{# -----------------------------------------------------------------------------
   compute_days_of_supply
   ----------------------
   Returns days-of-supply = on_hand_units / NULLIF(avg_daily_demand, 0).

   Caps the result at 999 to keep mart visualizations sane when demand is zero
   or near-zero (otherwise small denominators blow up).
   ----------------------------------------------------------------------------- #}
{% macro compute_days_of_supply(on_hand_col, avg_daily_demand_col, cap=999) %}
    case
        when {{ avg_daily_demand_col }} is null or {{ avg_daily_demand_col }} <= 0 then {{ cap }}
        else least(cast({{ on_hand_col }} / {{ avg_daily_demand_col }} as double), {{ cap }})
    end
{% endmacro %}
