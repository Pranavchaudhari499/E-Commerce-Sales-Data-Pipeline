# Architecture

This document describes the end-to-end architecture of the E-commerce Analytics
pipeline. It covers the data flow, the tech stack and the reasoning behind each
choice, and the physical data model.

## Overview

The system is a classic **ELT/ETL batch pipeline** that ingests raw, messy
e-commerce transaction data and turns it into a clean, analysable star schema
behind a SQL layer and an interactive dashboard.

```
                     +-----------------------------------------------------------+
                     |                        DATA SOURCE                        |
                     |   Raw e-commerce transactions export (messy, as produced  |
                     |   by a real POS / store backend) — CSV, seeded generator  |
                     +---------------------------+-------------------------------+
                                                 |
                                                 v
                     +-----------------------------------------------------------+
                     |       1. EXTRACT  (src/extract)                          |
                     |   - read raw file (auto-generate if missing)             |
                     |   - log source + extraction timestamp (provenance)       |
                     +---------------------------+-------------------------------+
                                                 |
                                                 v
                     +-----------------------------------------------------------+
                     |       2. VALIDATE (src/validation)                       |
                     |   - apply data-quality rules per field                   |
                     |   - hard-reject invalid rows with a readable reason      |
                     |   - surface duplicates / missing counts                 |
                     +---------------------------+-------------------------------+
                                                 |  (valid rows)
                                                 v
                     +-----------------------------------------------------------+
                     |       3. TRANSFORM (src/transform)                       |
                     |   - parse/normalise dates, prices, types                 |
                     |   - standardise categories & statuses                    |
                     |   - fill missing values with documented fallbacks        |
                     |   - de-duplicate, compute calculated fields              |
                     |   - fan out into star schema (fact + dimensions)         |
                     +---------------------------+-------------------------------+
                                                 |
                                                 v
                     +-----------------------------------------------------------+
                     |       4. LOAD (src/load)                                 |
                     |   - create schema (DDL)                                  |
                     |   - load dims then fact (FK-safe, idempotent)            |
                     |   - record pipeline run audit row                        |
                     +---------------------------+-------------------------------+
                                                 |
                          +----------------------+                 +-----------
                          |                      v                 v
                   SQLite (local demo)      PostgreSQL        Quality report
                          |                  (Docker prod)   (JSON + Markdown)
                          |                      |                 +
                          |                      v             rejected rows CSV
                          |             +-------------------+   (for inspection)
                          |             |  5. SQL ANALYTICS  |
                          |             |   sql/analytics.sql |
                          |             +-------------------+
                          |                      |
                          |                      v
                          +-------------------> v
                                                 |
                                                 v
                     +-----------------------------------------------------------+
                     |       6. VISUALIZE (dashboard/)                          |
                     |   - Dash interactive BI dashboard (KPIs, trends, drill)  |
                     +-----------------------------------------------------------+
```

## Stages in detail

### 1. Extract
`src/extract/extract.py`
- Reads the raw transactions file (CSV by default).
- If the file is absent, a synthetic, reproducible dataset is generated first
  (`src/extract/generate_data.py`). This generator deliberately injects the
  real-world messiness a business export would have (see Data Quality).
- Logs the source path, row count and extraction timestamp so every run is
  traceable.

### 2. Validate
`src/validation/rules.py`
- Runs a set of per-field rules and classifies each row as **valid** or **rejected**.
- Rejected rows are written to `data/quality/rejected_records.csv` with a human-readable
  `rejection_reason` (e.g. `invalid_date | missing_price`).
- Duplicates are detected and counted (removed later in transform).
- Produces a data-quality report (JSON + Markdown) summarising totals, rejects,
  duplicates, per-rule counts and per-column missing counts.

### 3. Transform
`src/transform/transform.py`
- Coerces and normalises every column:
  - dates -> `datetime`, parsed from several input formats (`2024-01-05`, `05/01/2024`, …)
  - prices -> `float`, parsing currency strings like `$1,299.00`
  - quantity -> integer
  - status -> canonical set (`completed`, `pending`, `cancelled`, `refunded`)
  - category -> standardised, taken from a product master catalogue so a single
    product never fragments into several categories
- Fills remaining missing values with **documented fallbacks** (e.g. unknown
  customer -> customer id `0`).
- Removes duplicate rows.
- Computes calculated fields: `line_total = quantity * unit_price` and a
  `revenue_flag` (only `completed`/`shipped` orders count as revenue).
- Builds the dimensional tables and the fact table.

### 4. Load
`src/load/load.py`
- Applies the star-schema DDL (`sql/schema.sql`).
- Loads dimension tables first, then the fact table (FK-safe ordering).
- Is idempotent: each run replaces the table contents cleanly.
- Inserts an audit row into `pipeline_runs` (status + timestamp).

### 5. Analyse
`sql/analytics.sql` + `src/analytics/queries.py`
- A library of business SQL queries (KPIs, revenue by month/product/category,
  AOV, regional and segment analysis, transaction drill-down).
- Written in portable ANSI SQL so the same queries run on SQLite and PostgreSQL.

### 6. Visualize
`dashboard/`
- A Dash web application that reads the analytics queries and renders:
  KPI cards, revenue trend, category & product performance, regional analysis,
  customer segments, and a searchable transaction table.

## Technology choices and the reason for each

| Technology | Why it was used |
|---|---|
| **Python 3** | Primary data-engineering language in the profile; the entire pipeline is Python/project-native. |
| **pandas / numpy** | Efficient in-memory cleaning, transformation and normalisation of tabular data. |
| **SQLAlchemy** | Database-agnostic connectivity; lets the same code target SQLite or PostgreSQL. |
| **SQLite** | Zero-install local demo engine; runs the whole pipeline without any server. |
| **PostgreSQL** | Production engine used in the Docker deployment — a realistic, industry-standard warehouse. |
| **Dash / Plotly** | Interactive BI dashboard with a pure-Python stack (replaces Tableau here since no licence is available; same SQL metrics feed either tool). |
| **Docker / Compose** | Reproducible production deployment (PostgreSQL + ETL + dashboard). |
| **GitHub Actions** | CI: runs the test suite and the full pipeline on every push; uploads the quality report as an artifact. |
| **pytest** | Unit tests for validation, transformation and load logic. |

No technology was added for decoration — each one is load-bearing in the pipeline.

## Data model (star schema)

```
 dim_product ────────┐
 dim_customer ───────┼──> fact_sales ──> dim_date
```

| Table | Purpose | Key columns |
|---|---|---|
| `dim_product` | Products and their category | `product_id` (PK), `product`, `category` |
| `dim_customer` | Customer master | `customer_id` (PK), `customer_name`, `segment`, `city`, `region` |
| `dim_date` | Calendar attributes | `date_id` (PK), `date`, `year`, `month`, `quarter`, `month_name`, `weekday_name`, `is_weekend` |
| `fact_sales` | One row per order line item | `sale_id` (PK), `order_id`, `date_id` (FK), `customer_id` (FK), `product_id` (FK), `quantity`, `unit_price`, `line_total`, `status`, `revenue_flag` |

This shape makes the analytics queries trivial and fast: almost every business
question is a grouped join between `fact_sales` and one or two dimensions.

## Data quality philosophy

The pipeline never silently drops or guesses. Every record is accounted for:

- **Valid rows** are loaded.
- **Rejected rows** are written to a file with a readable reason and counted in
  the quality report.
- **Duplicates** are detected, counted and removed during transformation.
- **Missing values** are either rejected (where they are structurally required)
  or filled with documented fallbacks (where a sensible default exists).

The synthetic generator injects ~8% of rows with at least one of: missing
prices/customers/categories, currency-string prices, malformed prices, invalid
or future dates, out-of-range quantities, duplicate lines, and dirty categorical
labels — so the cleaning logic is exercised on realistic (not perfect) input.