# =============================================================================
# Toolchain resolution
#
# This project strictly targets Python 3.13 via the `supply_env` pyenv virtualenv.
# We resolve every tool through the env prefix so things work whether or not
# pyenv-virtualenv auto-activation is configured in your shell.
#
# If `supply_env` doesn't exist yet, run:
#   pyenv install -s 3.13.3
#   pyenv virtualenv 3.13.3 supply_env
#   pyenv local supply_env
#
# Airflow + MLflow tracking server run in Docker (see docker-compose.yml). The
# Airflow image is custom-built from airflow/Dockerfile so that dbt, prophet,
# mlflow, and ortools are all on PATH inside BashOperator tasks.
# =============================================================================

PYENV_VENV       := supply_env
SUPPLY_ENV_PREFIX := $(shell pyenv prefix $(PYENV_VENV) 2>/dev/null)

PYTHON           := $(SUPPLY_ENV_PREFIX)/bin/python
PIP              := $(PYTHON) -m pip
DBT              := $(SUPPLY_ENV_PREFIX)/bin/dbt
RUFF             := $(SUPPLY_ENV_PREFIX)/bin/ruff
PYTEST           := $(SUPPLY_ENV_PREFIX)/bin/pytest
STREAMLIT        := $(SUPPLY_ENV_PREFIX)/bin/streamlit
SPHINX_BUILD     := $(SUPPLY_ENV_PREFIX)/bin/sphinx-build
SPHINX_AUTOBUILD := $(SUPPLY_ENV_PREFIX)/bin/sphinx-autobuild

# MLflow tracking URI for host-side runs (`make forecast`). Override by
# exporting MLFLOW_TRACKING_URI in your shell.
export MLFLOW_TRACKING_URI ?= http://localhost:5000

.PHONY: help _check-env install all-env generate dbt-deps dbt-build dbt-build-pre dbt-build-post \
        forecast optimize analyze pipeline app docs docs-build docs-clean test lint fmt clean \
        airflow-up airflow-down airflow-logs airflow-trigger mlflow-ui

# -----------------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -v '^_' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# -----------------------------------------------------------------------------
# Environment guardrail
# -----------------------------------------------------------------------------

_check-env:
	@command -v pyenv >/dev/null 2>&1 || { \
		echo "ERROR: pyenv is not installed."; \
		echo "       Install it first: https://github.com/pyenv/pyenv#installation"; \
		exit 1; \
	}
	@test -n "$(SUPPLY_ENV_PREFIX)" || { \
		echo "ERROR: pyenv virtualenv '$(PYENV_VENV)' not found."; \
		echo "       Run:"; \
		echo "         pyenv install -s 3.13.3"; \
		echo "         pyenv virtualenv 3.13.3 $(PYENV_VENV)"; \
		echo "         pyenv local $(PYENV_VENV)"; \
		exit 1; \
	}
	@$(PYTHON) -c "import sys; ok = sys.version_info[:2] == (3, 13); print(sys.version.split()[0]); sys.exit(0 if ok else 1)" >/tmp/.supply-pyver 2>/dev/null || { \
		echo "ERROR: $(PYENV_VENV) must be Python 3.13.x. Got: $$(cat /tmp/.supply-pyver 2>/dev/null || echo unknown)"; \
		echo "       Recreate the env:"; \
		echo "         pyenv uninstall -f $(PYENV_VENV)"; \
		echo "         pyenv install -s 3.13.3"; \
		echo "         pyenv virtualenv 3.13.3 $(PYENV_VENV)"; \
		echo "         pyenv local $(PYENV_VENV)"; \
		exit 1; \
	}
	@rm -f /tmp/.supply-pyver

# -----------------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------------

install: _check-env ## Install core + dev dependencies into supply_env
	$(PIP) install -e ".[dev]"

all-env: _check-env ## Install ALL extras (dev + dbt + streamlit + docs) -- one-shot bootstrap
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,dbt,streamlit,docs]"
	@echo "Python deps installed. Fetching dbt packages..."
	cd dbt_project && DBT_PROFILES_DIR=. $(DBT) deps
	@echo
	@echo "Environment ready. Next steps:"
	@echo "  make airflow-up   # start Airflow scheduler/webserver + MLflow tracking server in Docker"
	@echo "  make pipeline     # generate data, build dbt marts, run forecast + optimize"
	@echo "  make app          # start the Streamlit dashboard"
	@echo "  make docs         # browse the project documentation"

# -----------------------------------------------------------------------------
# Data pipeline
# -----------------------------------------------------------------------------

generate: _check-env ## Generate synthetic ERP-style supply chain data into data/raw/
	$(PYTHON) -m python.src.generate_data

dbt-deps: _check-env ## Install dbt packages (dbt-utils)
	cd dbt_project && DBT_PROFILES_DIR=. $(DBT) deps

dbt-build: _check-env ## Run dbt build (seeds + models + tests)
	cd dbt_project && DBT_PROFILES_DIR=. $(DBT) build

dbt-build-pre: _check-env ## Build dbt models that don't depend on stg_demand_forecast
	cd dbt_project && DBT_PROFILES_DIR=. $(DBT) build --exclude tag:needs_forecast

dbt-build-post: _check-env ## Build dbt models that depend on the forecast (refresh after forecast.py)
	cd dbt_project && DBT_PROFILES_DIR=. $(DBT) build --select tag:needs_forecast+

forecast: _check-env ## Run Prophet forecast for all SKUs and log to MLflow
	$(PYTHON) -m python.src.forecast

optimize: _check-env ## Run OR-Tools reorder-point optimization
	$(PYTHON) -m python.src.optimization

analyze: _check-env ## Run analysis orchestration (forecast + optimize + vendor scoring + alerts)
	$(PYTHON) -m python.src.analysis

pipeline: generate dbt-build-pre forecast dbt-build-post optimize analyze ## Full pipeline (host-side)

# -----------------------------------------------------------------------------
# Streamlit dashboard
# -----------------------------------------------------------------------------

app: _check-env ## Start the Streamlit dashboard on port 8501
	$(STREAMLIT) run streamlit_app/app.py --server.port 8501

# -----------------------------------------------------------------------------
# Airflow + MLflow (Docker Compose)
# -----------------------------------------------------------------------------

airflow-up: ## Start Airflow + MLflow tracking server in Docker
	docker compose up -d --build
	@echo "Airflow webserver: http://localhost:8080 (user/password from .env)"
	@echo "MLflow UI:         http://localhost:5000"

airflow-down: ## Stop and remove the Airflow + MLflow containers
	docker compose down

airflow-logs: ## Tail the Airflow scheduler logs
	docker compose logs -f airflow-scheduler

airflow-trigger: ## Manually trigger the supply_chain_pipeline DAG
	docker compose exec airflow-scheduler airflow dags trigger supply_chain_pipeline

mlflow-ui: ## Open the MLflow tracking UI in your browser
	@command -v open >/dev/null 2>&1 && open http://localhost:5000 || echo "Visit http://localhost:5000"

# -----------------------------------------------------------------------------
# Documentation (Sphinx)
# -----------------------------------------------------------------------------

docs: _check-env ## Build and serve docs with live reload (port 8000)
	$(SPHINX_AUTOBUILD) docs docs/_build/html --port 8000 --open-browser

docs-build: _check-env ## One-shot build of docs to docs/_build/html
	$(SPHINX_BUILD) -b html docs docs/_build/html

docs-clean: ## Remove generated documentation artifacts
	rm -rf docs/_build

# -----------------------------------------------------------------------------
# Quality
# -----------------------------------------------------------------------------

test: _check-env ## Run pytest
	$(PYTEST)

lint: _check-env ## Lint with ruff
	$(RUFF) check .

fmt: _check-env ## Format with ruff
	$(RUFF) format .

# -----------------------------------------------------------------------------
# Cleanup
# -----------------------------------------------------------------------------

clean: ## Remove generated data, dbt artifacts, and MLflow runs
	rm -rf data/raw/*.parquet data/forecast/*.parquet data/supply.duckdb data/mlruns/* \
	       dbt_project/target dbt_project/dbt_packages dbt_project/logs mlflow.db
