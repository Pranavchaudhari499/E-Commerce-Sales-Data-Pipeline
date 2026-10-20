"""Tests for the load stage (schema creation + row loading)."""
from __future__ import annotations

import pandas as pd

from src.load.load import get_engine, load, run_schema
from src.transform.transform import transform
from src.validation.rules import validate
from sqlalchemy import text


def _sample_transformed():
    df = pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3"],
            "order_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "customer_id": ["1001", "1002", "1003"],
            "product": ["Wireless Mouse M12", "Desk Organizer", "Coffee Maker 12-Cup"],
            "category": ["Electronics", "Office", "Kitchen"],
            "unit_price": [24.99, 18.75, 74.99],
            "quantity": [1, 2, 1],
            "status": ["completed", "completed", "completed"],
        }
    )
    v = validate(df)
    return transform(v.valid)


def test_schema_tables_created(temp_db_env):
    engine = get_engine()
    run_schema(engine)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )
        }
    assert {"dim_product", "dim_customer", "dim_date",
            "fact_sales"} <= tables


def test_load_populates_tables(temp_db_env):
    engine = get_engine()
    summary = load(_sample_transformed(), engine)
    assert summary["dim_product"] >= 3
    assert summary["fact_sales"] == 3
    with engine.connect() as conn:
        fact_count = conn.execute(
            text("SELECT COUNT(*) FROM fact_sales")
        ).scalar()
        assert fact_count == 3


def test_load_is_idempotent(temp_db_env):
    engine = get_engine()
    load(_sample_transformed(), engine)
    # Second run replaces contents rather than duplicating.
    load(_sample_transformed(), engine)
    with engine.connect() as conn:
        fact_count = conn.execute(
            text("SELECT COUNT(*) FROM fact_sales")
        ).scalar()
    assert fact_count == 3
