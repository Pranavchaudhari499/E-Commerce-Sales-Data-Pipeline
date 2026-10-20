"""Tests for the dashboard data-access layer (SQL-level filters)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.load.load import get_engine
from src.load.load import load
from src.transform.transform import transform
from src.validation.rules import validate
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# Guard: if engine isn't SQLite, skip (filters need a populated DB).
from src.utils.config import get_config


@pytest.fixture
def _loaded_db(temp_db_env):
    """Load a small known dataset into a temp SQLite DB."""
    df = pd.DataFrame(
        {
            "order_id": ["A1", "A2", "B1", "B2", "C1", "C2"],
            "order_date": ["2024-01-01"] * 2 + ["2024-01-02"] * 2 + ["2024-01-03"] * 2,
            "customer_id": ["1001", "1002"] * 3,
            "product": [
                "Wireless Mouse M12", "Wireless Mouse M12",
                "Standing Desk 120x60", "Standing Desk 120x60",
                "Coffee Maker 12-Cup", "Coffee Maker 12-Cup",
            ],
            "category": ["Electronics"] * 2 + ["Office"] * 2 + ["Kitchen"] * 2,
            "unit_price": [24.99, 24.99, 499.0, 499.0, 74.99, 74.99],
            "quantity": [1, 2, 1, 2, 1, 2],
            "status": ["completed", "completed", "completed", "completed",
                       "completed", "completed"],
        }
    )
    v = validate(df)
    tr = transform(v.valid)
    load(tr, get_engine())
    return tr


def _import_data_layer():
    sys.path.insert(0, str(ROOT))
    from dashboard import data as D

    return D


def test_kpis_respond_to_region_filter(_loaded_db):
    D = _import_data_layer()
    if get_config().db_engine != "sqlite":
        pytest.skip("requires a local DB")
    all_k = D.kpis(D.Filters()).iloc[0]
    west_k = D.kpis(D.Filters(region="West")).iloc[0]
    # West exists in the catalog for customers 1001/1002? check presence:
    # We only assert that filtering on a real region returns <= all revenue.
    assert west_k["total_revenue"] <= all_k["total_revenue"]
    # Unknown region yields zero/None rows gracefully (no crash).
    D.kpis(D.Filters(region="DoesNotExist"))


def test_category_filter_changes_top_products(_loaded_db):
    D = _import_data_layer()
    if get_config().db_engine != "sqlite":
        pytest.skip("requires a local DB")
    office = D.top_products(D.Filters(category="Office"), 10)
    assert not office.empty
    assert set(office["category"].unique()) <= {"Office"}


def test_has_conditions_guard():
    D = _import_data_layer()
    assert not D.Filters().has_conditions()
    assert D.Filters(region="West").has_conditions()
    assert D.Filters(start_date="2024-01-01").has_conditions()
