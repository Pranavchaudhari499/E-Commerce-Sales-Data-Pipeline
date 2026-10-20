"""Tests for the extraction stage."""
from __future__ import annotations

from src.extract.generate_data import generate_transactions
from src.extract.extract import read_raw, extract


def test_generator_is_reproducible():
    a = generate_transactions(n_rows=5000, seed=7)
    b = generate_transactions(n_rows=5000, seed=7)
    assert a.equals(b)


def test_generator_creates_messy_data():
    df = generate_transactions(n_rows=5000, seed=7)
    # Deliberately not perfect: has missing values.
    assert df.isna().sum().sum() > 0
    # Contains currency-string + numeric prices in the same column.
    assert df["unit_price"].astype(str).str.contains(r"\$\d").any()
    # Column set matches expectation.
    expected = {"order_id", "order_date", "customer_id", "product",
                "category", "unit_price", "quantity", "status"}
    assert expected <= set(df.columns)


def test_extract_roundtrip_csv(tmp_path):
    from src.extract.generate_data import write_transactions

    df = generate_transactions(n_rows=3000, seed=3)
    path = tmp_path / "raw.csv"
    write_transactions(df, path, fmt="csv")
    loaded = read_raw(path)
    assert len(loaded) == len(df)
    assert "order_id" in loaded.columns
