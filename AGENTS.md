# AGENTS.md

Concise reference for AI coding agents and contributors working with this repo.
For full human-facing docs see [README.md](./README.md) and
[docs/architecture.md](./docs/architecture.md).

## What this is

**E-commerce Sales Analytics — Automated Data Pipeline.** An end-to-end ETL
pipeline that converts messy raw e-commerce transaction CSV into a clean star
schema in a SQL database, runs business analytics, and serves a Dash dashboard.

- Language: Python 3.11
- Stack: pandas/numpy/pyarrow ETL, SQLAlchemy, Dash/Plotly dashboard, SQLite
  (local demo) or PostgreSQL (Docker)
- Tests: pytest
- License: MIT

## Quick commands (from repo root)

```bash
# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the full ETL pipeline (SQLite, default local engine)
cp .env.example .env            # DB_ENGINE=sqlite is the default
python pipeline.py

# Run pipeline with a fresh synthetic dataset
python pipeline.py --generate 20000

# Run the interactive dashboard (default http://127.0.0.1:8050)
python dashboard/app.py

# Run the test suite
python -m pytest

# Full Docker/PostgreSQL stack
docker compose up --build
```

## Environment config

- Copy `.env.example` → `.env`. Do NOT commit real `.env` values (it's gitignored).
- `DB_ENGINE` = `sqlite` (local demo) or `postgresql` (Docker/prod).
- `RAW_TRANSACTIONS` defaults to `data/raw/transactions.csv`; if absent, the
  pipeline generates a fresh synthetic dataset (see `--generate`).
- `GENERATE_ROWS`, `RANDOM_SEED` control synthetic data generation.

## Repository layout (key modules)

```
pipeline.py                 # CLI entry point (--generate / --sqlite / --postgresql / --seed)
src/
  etl_pipeline.py           # run_pipeline(): orchestrates extract->validate->transform->load
  extract/                  # read raw CSV + generate synthetic data (generate_data.py)
  validation/               # data-quality rules + rejected-rows reporting
  transform/                # clean, standardize, de-dup, star-schema transforms
  load/                     # SQLite/Postgres load (LoadResult)
  analytics/queries.py      # business KPI SQL
  utils/                    # config (env), logging
dashboard/app.py            # Dash app (run: python dashboard/app.py)
sql/                        # schema.sql, analytics.sql
tests/                      # pytest suite (conftest + 5 test modules)
data/raw, data/processed, data/quality   # input, star-schema DB, quality reports
.github/workflows/ci.yml    # CI: pytest + full SQLite pipeline run
```

## Testing

- Config: `pytest.ini` (testpaths = tests, pythonpath = .).
- Run all: `python -m pytest`.
- CI runs the unit suite then `python pipeline.py --generate 20000 --sqlite`
  and uploads the quality report as an artifact.

## Outputs / artifacts

- `data/processed/sales.db` — loaded star schema (SQLite).
- `data/quality/quality_report.md` + `rejected_records.csv` — what passed/failed
  validation and why.
- `examples/` — sample report, sample rejected rows, dashboard screenshot.

## Contribution notes

- Tests live under `tests/` and must keep passing (`python -m pytest`).
- Keep `pipeline.py` runnable end-to-end on SQLite — it's the CI-proven path.
- Config is read through `.env` via `src/utils/config.py`; keep `.env.example`
  in sync when adding new settings.
- Docker: `Dockerfile` runs the ETL one-shot against PostgreSQL by default;
  `docker-compose.yml` brings up db + etl + dashboard.
