#!/usr/bin/env python3
"""Command-line entry point for the E-commerce ETL pipeline.

Run the full pipeline with default settings:

    python pipeline.py

Optional flags:
    --generate [n]   Generate a fresh synthetic dataset of n rows first
    --sqlite         Force the SQLite engine (default local demo engine)
    --postgresql     Force the PostgreSQL engine
    --seed <int>     Random seed for a reproducible dataset

The `--generate` flag re-creates `data/raw/transactions.parquet` from scratch,
which is useful to demonstrate handling of the messy source data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure `src` is importable when running from the project root.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.logging import setup_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the e-commerce ETL pipeline")
    parser.add_argument(
        "--generate",
        nargs="?",
        const=100000,
        type=int,
        metavar="N",
        help="Generate a fresh synthetic dataset (optionally N rows) before running",
    )
    parser.add_argument(
        "--sqlite", action="store_true", help="Force the SQLite engine"
    )
    parser.add_argument(
        "--postgresql", action="store_true", help="Force the PostgreSQL engine"
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    args = parser.parse_args()

    setup_logging()

    if args.generate is not None:
        from src.extract.generate_data import generate_transactions, write_transactions

        n = args.generate
        seed = args.seed if args.seed is not None else 42
        df = generate_transactions(n_rows=n, seed=seed)
        out = ROOT / "data" / "raw" / "transactions.csv"
        write_transactions(df, out)
        print(f"Generated {len(df)} raw rows -> {out}")

    engine = None
    if args.sqlite:
        engine = "sqlite"
    elif args.postgresql:
        engine = "postgresql"

    from src.etl_pipeline import run_pipeline

    result = run_pipeline(db_engine=engine)
    print("\n================ PIPELINE SUMMARY ================")
    print(f"Extracted rows   : {result.extract_rows}")
    print(f"Valid rows       : {result.valid_rows}")
    print(f"Rejected rows    : {result.rejected_rows}")
    print(f"Duplicate rows   : {result.duplicate_rows}")
    print(f"Rejected file    : {result.rejected_file}")
    print(f"Quality report   : {result.quality_report}")
    print(f"Loaded (per table):")
    for table, count in result.loaded_rows.items():
        print(f"    {table:<14} {count}")
    print(f"Duration         : {result.duration_seconds}s")
    print("=================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
