"""Extraction stage.

Reads raw transactions from disk (parquet), records when extraction happened,
and handles the case where the source file is missing by triggering generation.
Also captures a lightweight provenance summary so every row can be traced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.utils.config import get_config, get_paths
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class ExtractResult:
    """Result of the extraction stage."""

    df: pd.DataFrame
    source: str
    extracted_at: str
    row_count: int
    columns: list[str]


def resolve_raw_path() -> Path:
    cfg = get_config()
    p = Path(cfg.raw_transactions)
    if not p.is_absolute():
        p = get_paths().root / p
    return p


def read_raw(path: Path | None = None) -> pd.DataFrame:
    """Read the raw transactions file, generating it if it does not exist."""
    path = Path(path) if path else resolve_raw_path()

    if not path.exists():
        log.warning("Source file %s not found — generating synthetic dataset.", path)
        _generate(path)

    ext = path.suffix.lower()
    if ext in (".parquet",):
        df = pd.read_parquet(path)
    elif ext == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported raw data format: {ext}")

    log.info("Extracted %s rows from %s", len(df), path)
    return df


def _generate(path: Path) -> None:
    from src.extract.generate_data import generate_transactions, write_transactions

    cfg = get_config()
    df = generate_transactions(n_rows=cfg.generate_rows, seed=cfg.random_seed)
    write_transactions(df, path)


def extract(path: Path | None = None) -> ExtractResult:
    """Run the extraction stage end-to-end."""
    source = resolve_raw_path() if path is None else Path(path)
    df = read_raw(source)
    return ExtractResult(
        df=df,
        source=str(source),
        extracted_at=datetime.now().isoformat(timespec="seconds"),
        row_count=len(df),
        columns=list(df.columns),
    )
