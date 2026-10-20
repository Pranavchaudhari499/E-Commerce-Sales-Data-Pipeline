"""Load stage.

Creates the database schema, loads the dimension and fact tables, and records
each pipeline run in a `pipeline_runs` table (execution status / timestamps).

Supports both SQLite (local zero-install demo) and PostgreSQL (production /
Docker) by issuing portable ANSI SQL.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from src.transform.transform import TransformedData
from src.utils.config import get_paths, database_url
from src.utils.logging import get_logger

log = get_logger(__name__)

TABLE_ORDER = ["dim_product", "dim_customer", "dim_date", "fact_sales"]


def get_engine() -> Engine:
    url = database_url()
    log.info("Connecting to database engine (url: %s...)", url.split("@")[-1] if "@" in url else url)
    engine = create_engine(url)
    return engine


def run_schema(engine: Engine) -> None:
    """Apply the star-schema DDL (idempotent)."""
    schema_file = get_paths().sql / "schema.sql"
    ddl = schema_file.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for statement in ddl.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
    log.info("Schema created/verified")


def load(data: TransformedData, engine: Engine | None = None) -> dict:
    """Load transformed (star-schema) tables into the database.

    Returns a small summary dict for pipeline reporting.
    """
    engine = engine or get_engine()
    run_schema(engine)

    frames = {
        "dim_product": data.dim_product,
        "dim_customer": data.dim_customer,
        "dim_date": data.dim_date,
        "fact_sales": data.fact_sales,
    }

    loaded = {}
    with engine.begin() as conn:
        # Delete in reverse dependency order (children before parents) so the
        # fact table is cleared before the dimensional tables it references.
        for table in reversed(TABLE_ORDER):
            conn.execute(text(f"DELETE FROM {table}"))
        # Insert parents first, then the fact table.
        for table in TABLE_ORDER:
            frames[table].to_sql(
                table,
                con=conn,
                if_exists="append",
                index=False,
                method="multi",
            )
            loaded[table] = int(len(frames[table]))
            log.info("Loaded %s rows into %s", loaded[table], table)

    # Record the pipeline run for auditability.
    record_run(engine, status="SUCCESS", details=str(loaded))
    return loaded


def record_run(engine: Engine, status: str, details: str = "") -> None:
    """Insert a row into pipeline_runs (created on demand).

    Dialect-aware: SQLite uses AUTOINCREMENT, PostgreSQL uses GENERATED
    (identity) so the table definition is valid on both engines.
    """
    dialect = engine.dialect.name
    if dialect == "sqlite":
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
    else:
        pk = "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"

    create = f"""
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id          {pk},
        ran_at          TEXT NOT NULL,
        status          TEXT NOT NULL,
        rows_loaded     INTEGER DEFAULT 0,
        details         TEXT
    )
    """
    with engine.begin() as conn:
        conn.execute(text(create))
        conn.execute(
            text(
                "INSERT INTO pipeline_runs (ran_at, status, details) "
                "VALUES (:t, :s, :d)"
            ),
            {
                "t": datetime.now().isoformat(timespec="seconds"),
                "s": status,
                "d": details,
            },
        )
