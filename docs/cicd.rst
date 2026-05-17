CI / CD
=======

GitHub Actions workflow
-----------------------

``.github/workflows/ci.yml`` runs on every push and pull request to any
branch. The single ``lint-and-test`` job:

1. Checks out the repo.
2. Sets up Python 3.13 via ``actions/setup-python`` with pip caching keyed
   off ``pyproject.toml``.
3. Installs ``-e ".[dev,dbt,streamlit]"`` (skipping the ``docs`` extra for
   speed).
4. Runs ``ruff check .`` and ``ruff format --check .`` -- the formatter is
   enforced, not just suggested.
5. Runs the **dbt-independent test subset:**

   .. code-block:: bash

       pytest tests/test_metrics.py tests/test_safety_stock.py tests/test_vendor_scoring.py

   These tests don't need a built DuckDB warehouse, so they're fast and
   appropriate for the CI loop. The dbt-dependent tests
   (``test_dbt_pipeline.py``, ``test_generate_data.py``, ``test_forecast.py``)
   require ``make pipeline`` to materialize ``data/supply.duckdb``; they
   run locally and on full pre-merge integration runs.

6. ``cd dbt_project && dbt deps && dbt parse`` -- validates dbt project
   syntax (sources, refs, jinja, tests) without ever touching DuckDB.

A concurrency group on ``${{ github.workflow }}-${{ github.ref }}`` cancels
in-progress runs when a new commit lands on the same branch, which keeps
the CI minute usage low.

Skipping prophet in CI
~~~~~~~~~~~~~~~~~~~~~~

Prophet's ``cmdstanpy`` backend builds C++ on first install (~3 min on a
GitHub Actions runner). We accept that hit because it lets us actually
import ``forecast.py`` in CI to validate it parses; alternative designs
(skip Prophet in CI, mock it in tests) are deferred until install time
becomes a real problem.

Dependabot
----------

``.github/dependabot.yml`` schedules weekly Monday updates for both pip
and GitHub Actions. Pip updates are grouped to keep the PR queue
manageable:

* ``ml`` group -- prophet, mlflow, ortools, scipy, scikit-learn
* ``dbt`` group -- dbt-core, dbt-duckdb (and any other dbt-* adapters)
* ``streamlit`` group -- streamlit, plotly
* ``dev`` group -- pytest*, ruff, mypy

This means if the ML libraries all update together (which they often do),
a single PR covers them rather than five overlapping ones.

Branch protection (recommended)
-------------------------------

The repo isn't auto-configured here, but the recommended setup for the
default branch:

* Require ``lint-and-test`` to pass before merging.
* Require at least one approving review.
* Require linear history (squash or rebase merges only).

Combined with the Dependabot grouping, this keeps the merge queue
predictable.
