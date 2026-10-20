"""Central configuration for the ETL pipeline.

All environment-driven settings live here so that changing the database
engine, file paths, or pipeline options is a single-point edit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of the `src` package directory.
# config.py -> utils -> src -> <project root>
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env only if present; missing file is fine (defaults are used).
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Paths:
    """Well-known filesystem locations used by the pipeline."""

    root: Path = PROJECT_ROOT
    data_raw: Path = PROJECT_ROOT / "data" / "raw"
    data_processed: Path = PROJECT_ROOT / "data" / "processed"
    data_quality: Path = PROJECT_ROOT / "data" / "quality"
    sql: Path = PROJECT_ROOT / "sql"
    src: Path = PROJECT_ROOT / "src"


@dataclass(frozen=True)
class Config:
    """Runtime configuration.

    Plain defaults only — the dataclass is constructed fresh from the current
    environment in :func:`get_config` so that runtime overrides (e.g. switching
    the DB engine, or tests pointing at a temp file) always take effect.
    """

    db_engine: str = "sqlite"
    sqlite_db_path: str = "data/processed/sales.db"
    postgres_host: str = "localhost"
    postgres_port: str = "5432"
    postgres_db: str = "ecommerce"
    postgres_user: str = "ecommerce"
    postgres_password: str = "ecommerce"

    raw_transactions: str = "data/raw/transactions.csv"
    generate_rows: int = 100000
    random_seed: int = 42


@dataclass(frozen=True)
class Dimensions:
    """Domain constants shared across the pipeline (kept consistent everywhere)."""

    # Upper bound on a valid unit price (anything above is treated as invalid).
    max_unit_price: float = 10000.0
    max_quantity: int = 1000

    # Valid categorical values (anything else is standardised to the closest
    # match or rejected).
    valid_statuses = {"completed", "pending", "cancelled", "refunded"}


def get_config() -> Config:
    """Build Config from the *current* environment (read fresh each call)."""
    return Config(
        db_engine=os.getenv("DB_ENGINE", "sqlite").strip().lower(),
        sqlite_db_path=os.getenv("SQLITE_DB_PATH", "data/processed/sales.db"),
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=os.getenv("POSTGRES_PORT", "5432"),
        postgres_db=os.getenv("POSTGRES_DB", "ecommerce"),
        postgres_user=os.getenv("POSTGRES_USER", "ecommerce"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "ecommerce"),
        raw_transactions=os.getenv("RAW_TRANSACTIONS", "data/raw/transactions.csv"),
        generate_rows=int(os.getenv("GENERATE_ROWS", "100000")),
        random_seed=int(os.getenv("RANDOM_SEED", "42")),
    )


def get_paths() -> Paths:
    return Paths()


def build_sqlite_url(path: str | Path) -> str:
    """Build a SQLAlchemy URL for a local SQLite file (creates parent dirs)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve()}"


def build_postgres_url(cfg: Config) -> str:
    return (
        f"postgresql+psycopg2://{cfg.postgres_user}:{cfg.postgres_password}"
        f"@{cfg.postgres_host}:{cfg.postgres_port}/{cfg.postgres_db}"
    )


def database_url(cfg: Config | None = None) -> str:
    """Return the SQLAlchemy connection URL for the configured engine."""
    cfg = cfg or get_config()
    if cfg.db_engine == "postgresql":
        return build_postgres_url(cfg)
    if cfg.db_engine == "sqlite":
        return build_sqlite_url(cfg.sqlite_db_path)
    raise ValueError(
        f"Unsupported DB_ENGINE '{cfg.db_engine}'. Use 'sqlite' or 'postgresql'."
    )
