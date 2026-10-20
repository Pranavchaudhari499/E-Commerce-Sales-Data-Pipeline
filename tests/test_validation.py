"""Tests for the validation stage (data-quality rules)."""
from __future__ import annotations

import pandas as pd

from src.validation.rules import validate, _normalise_price

REQUIRED = {
    "order_id": ["O1", "O2", "O3"],
    "order_date": ["2024-01-15", "2024-01-16", "2024-01-17"],
    "customer_id": ["1001", "1002", "1003"],
    "product": ["A", "B", "C"],
    "category": ["Electronics", "Office", "Kitchen"],
    "unit_price": [10.0, 20.0, 30.0],
    "quantity": [1, 2, 3],
    "status": ["completed", "completed", "completed"],
}


def test_clean_rows_pass_validation():
    df = pd.DataFrame(REQUIRED)
    result = validate(df)
    assert len(result.valid) == 3
    assert len(result.rejected) == 0


def test_missing_order_id_is_rejected():
    df = pd.DataFrame(REQUIRED)
    df.loc[0, "order_id"] = None
    result = validate(df)
    assert len(result.rejected) == 1
    assert "missing_order_id" in result.rejected.iloc[0]["rejection_reason"]


def test_invalid_date_rejected():
    df = pd.DataFrame(REQUIRED)
    df.loc[0, "order_date"] = "2025-13-40"
    result = validate(df)
    assert len(result.rejected) == 1
    assert "invalid_date" in result.rejected.iloc[0]["rejection_reason"]


def test_invalid_price_rejected():
    df = pd.DataFrame(REQUIRED)
    df.loc[0, "unit_price"] = "abc"
    result = validate(df)
    assert len(result.rejected) == 1
    assert "invalid_price" in result.rejected.iloc[0]["rejection_reason"]


def test_negative_and_huge_quantity_rejected():
    df = pd.DataFrame(REQUIRED)
    df.loc[0, "quantity"] = -3
    df.loc[1, "quantity"] = 99999
    result = validate(df)
    assert len(result.rejected) == 2
    assert all(
        "invalid_quantity" in r for r in result.rejected["rejection_reason"]
    )


def test_duplicates_detected():
    df = pd.concat(
        [pd.DataFrame(REQUIRED), pd.DataFrame(REQUIRED)], ignore_index=True
    )
    result = validate(df)
    # Duplicates are surfaced in the report but kept through validation
    # (they are removed during transformation).
    assert result.duplicate_count == 3
    assert len(result.valid) == 6  # not auto-rejected


def test_currency_string_price_parses():
    assert _normalise_price("$24.99") == 24.99
    assert _normalise_price("$1,299.00") == 1299.00
    assert _normalise_price(42.5) == 42.5
    assert _normalise_price("abc") is None
    assert _normalise_price(None) is None
