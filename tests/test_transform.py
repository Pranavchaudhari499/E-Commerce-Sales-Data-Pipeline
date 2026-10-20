"""Tests for the transformation stage."""
from __future__ import annotations

import pandas as pd

from src.transform.transform import transform, _parse_price_series
from src.validation.rules import validate


def test_transform_produces_star_schema(transformed_result):
    assert {"dim_product", "dim_customer", "dim_date",
            "fact_sales"} <= set(transformed_result.__dict__.keys())
    # Fact should have no null surrogate keys.
    assert transformed_result.fact_sales["product_id"].notna().all()
    assert transformed_result.fact_sales["date_id"].notna().all()
    assert transformed_result.fact_sales["customer_id"].notna().all()


def test_line_total_calculated(transformed_result):
    fact = transformed_result.fact_sales
    expected = (fact["quantity"] * fact["unit_price"]).round(2)
    assert (fact["line_total"] - expected).abs().max() < 0.01


def test_price_strings_parsed(transformed_result):
    prices = set(transformed_result.fact_sales["unit_price"].dropna())
    assert all(isinstance(p, float) for p in prices)


def test_categories_standardised(transformed_result):
    cats = set(transformed_result.dim_product["category"])
    assert cats <= {"Electronics", "Office", "Kitchen", "Fitness", "Other"}


def test_duplicates_removed():
    # Two identical rows should collapse to one in the fact table.
    df = pd.DataFrame(
        {
            "order_id": ["O1", "O1", "O2"],
            "order_date": ["2024-05-01", "2024-05-01", "2024-05-02"],
            "customer_id": ["1001", "1001", "1002"],
            "product": ["Wireless Mouse M12", "Wireless Mouse M12", "Desk Organizer"],
            "category": ["Electronics", "Electronics", "Office"],
            "unit_price": [24.99, 24.99, 18.75],
            "quantity": [1, 1, 2],
            "status": ["completed", "completed", "completed"],
        }
    )
    v = validate(df)
    tr = transform(v.valid)
    assert tr.dropped_duplicates == 1
    assert len(tr.fact_sales) == 2


def test_missing_customer_filled():
    df = pd.DataFrame(
        {
            "order_id": ["O1"],
            "order_date": ["2024-05-01"],
            "customer_id": [None],
            "product": ["Wireless Mouse M12"],
            "category": ["Electronics"],
            "unit_price": [24.99],
            "quantity": [1],
            "status": ["completed"],
        }
    )
    v = validate(df)
    tr = transform(v.valid)
    # customer_id filled with 0 fallback, which resolves in the customer dim.
    assert tr.fact_sales["customer_id"].iloc[0] in tr.dim_customer["customer_id"].values


def test_parse_price_series_handles_mixed():
    s = pd.Series([24.99, "$24.99", "1,299.00", "abc", None])
    parsed = _parse_price_series(s)
    assert parsed.iloc[0] == 24.99
    assert parsed.iloc[1] == 24.99
    assert parsed.iloc[2] == 1299.0
    assert pd.isna(parsed.iloc[3])
    assert pd.isna(parsed.iloc[4])
