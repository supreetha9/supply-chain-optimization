Optimization Methodology
========================

Implemented in ``python/src/optimization.py``. Every (SKU, warehouse) pair
with non-zero average demand gets its own optimization. The benchmark is
the textbook safety-stock formula in ``python/src/safety_stock.py``.

Decision variable
-----------------

For each pair we choose a single scalar:

.. code-block:: text

    R = reorder_point (units)

When inventory_position drops below R, a purchase order is placed.

Objective function
------------------

We minimize total expected cost over one lead-time window:

.. code-block:: text

    minimize  expected_holding_cost(R) + expected_stockout_cost(R)

with components:

* **Expected holding cost** = ``max(R - mu_L, 0) * h * L``

  where ``mu_L = avg_daily_demand * L`` is the mean lead-time demand,
  ``h`` is the holding cost per unit per day, and ``L`` is the lead time
  in days.

* **Expected stockout cost** = ``sigma_L * (phi(z) - z * (1 - Phi(z))) * p``

  where ``sigma_L = sigma_d * sqrt(L)`` is the lead-time demand standard
  deviation, ``z = (R - mu_L) / sigma_L`` is the standardized buffer
  level, ``phi/Phi`` are the standard-normal pdf/cdf, and ``p`` is the
  stockout penalty per unit short. This is the standard
  *partial-expectation tail* used in newsvendor pricing.

Constraints
-----------

1. **Service level floor:** ``R >= mu_L + z* * sigma_L`` where
   ``z* = norm.ppf(target_service_level)``. Service-level targets come from
   the ``service_level_targets`` seed (A: 0.98, B: 0.95, C: 0.90).

2. **Capacity ceiling:** ``R <= warehouse_capacity / 2``. Prevents the
   optimizer from blowing through a warehouse for a single SKU.

Solver choice
-------------

Google OR-Tools' **GLOP** linear-programming solver. We discretize R into
25 candidate points between the service-level floor and the capacity
ceiling, then ask GLOP to pick the convex combination of candidates that
minimizes expected total cost. Because the cost function is convex over
the candidate range, the LP recovers the true continuous optimum to
within the grid resolution (improvable by raising ``candidates``).

Why not GLOP for the entire LP / MIP?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We could rewrite the per-SKU optimization as a continuous LP by
piecewise-linearizing the cost function. The current approach is more
robust because the cost has a non-trivial probabilistic component
(``phi``, ``Phi``) that's awkward to encode in pure LP form. The grid +
GLOP combination is the simplest correct formulation for a portfolio
demo; for production at thousands of SKUs an analytic newsvendor solution
is faster.

Benchmark: the textbook formula
-------------------------------

We compare the OR-Tools choice to the canonical safety-stock formula:

.. code-block:: text

    safety = z * sqrt(L) * sigma_d
    R_textbook = avg_daily_demand * L + safety

The benchmark uses a blanket 0.99 service level (a common
"set-it-and-forget-it" default). The optimizer respects the
per-ABC-class targets (0.90 / 0.95 / 0.98), so for B and C SKUs it
should generate real cost savings by being less conservative. Total
savings across ~1500 series typically lands in the **mid-four-figure
USD range over one lead-time window**.

Sensitivity analysis
--------------------

The Streamlit Replenishment page lets the user toggle:

* OR-Tools only
* Textbook only
* Both (box-plot comparison by ABC class)

and view the cost-savings table sorted by per-SKU savings.
