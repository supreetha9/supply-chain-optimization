Business Problem
================

Pain points the platform addresses
----------------------------------

Mid-market consumer-goods companies and B2B distributors run on a small
number of perpetually competing supply-chain levers. Getting any one of
them wrong has six- or seven-figure consequences:

* **Stockouts** -- when a high-velocity SKU goes to zero, the customer goes
  to a competitor; lost revenue and brand damage compound.
* **Excess inventory** -- working capital tied up in slow movers carries
  storage cost, obsolescence risk, and writedown exposure.
* **Vendor risk** -- a single supplier missing a contracted lead time can
  ripple into 1000+ partial shipments downstream and tank OTIF.
* **OTIF (On-Time-In-Full)** misses -- customers track this religiously and
  trigger SLA penalties or contract churn.
* **Forecast drift** -- planners using stale or unmonitored forecasts
  compound bullwhip distortions across the network.

Target user personas
--------------------

* **S&OP planner** -- weekly review meeting; needs forecast accuracy by SKU,
  reorder candidates, vendor exceptions.
* **Operations director** -- monthly executive review; needs OTIF, fill
  rate, backlog, capacity utilization across regions.
* **Procurement lead** -- vendor reviews and contract renewals; needs
  composite vendor scores backed by lead-time variance and defect data.
* **Supply chain analyst** -- ad-hoc deep dives; needs the underlying dbt
  marts and the MLflow run history to investigate model degradation.

Success metrics
---------------

The platform succeeds when it materially improves three numbers:

1. **Service level attainment** (OTIF + fill rate) -- target 95%+ for
   ABC-A SKUs, 90%+ for B/C.
2. **Inventory turnover** -- 8-12x for fast movers; flag any SKU with
   <2 turns and >180 days of supply as excess.
3. **Composite vendor score** -- track the 90th-percentile vendor score
   month over month; an upward trend signals supply-base degradation.
