"""Shared pytest fixtures.

Routes database writes to a throwaway SQLite file so tests never touch the
real database or a live PostgreSQL server.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from src.transform.transform import TransformedData
from src.utils.config import get_paths
import pandas as pd

@pytest.fixture(scope="session")
def sample_valid_df() -> pd.DataFrame:
    """A small, clean-ish frame that passes validation.

    Includes edge values that must survive transformation (dollar-string
    prices, ugly dates) to exercise the normalisation logic.
    """
    return pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3", "O4", "O5"],
            "order_date": ["2024-01-15", "15/01/2024", "2024-02-20",
                           "2024-03-05", "2024-03-10"],
            "customer_id": ["1001", "1002", "1003", "1001", "1004"],
            "product": ["Wireless Mouse M12"] * 5,
            "category": ["Electronics", "electronics", "Electronics ",
                         "ELECTRONICS", "Electronics"],
            "unit_price": [24.99, "$24.99", 24.99, "24.99", 24.99],
            "quantity": [1, 2, 3, 1, 4],
            "status": ["completed", "completed", "shipped", "completed", "cancelled"],
        }
    )


@pytest.fixture
def transformed_result(sample_valid_df) -> TransformedData:
    from src.transform.transform import transform
    from src.validation.rules import validate

    validation = validate(sample_valid_df)
    return transform(validation.valid)


@pytest.fixture(scope="function")
def temp_db_env(tmp_path) -> str:
    """Point the config at a temp SQLite DB and return its URL."""
    db_file = tmp_path / "test_sales.db"
    os.environ["DB_ENGINE"] = "sqlite"
    os.environ["SQLITE_DB_PATH"] = str(db_file)
    yield str(db_file)
    os.environ.pop("SQLITE_DB_PATH", None)
    os.environ.pop("DB_ENGINE", None)


# Re-export paths helper so tests can reference known project dirs.
def project_root() -> str:
    return str(get_paths().root)
