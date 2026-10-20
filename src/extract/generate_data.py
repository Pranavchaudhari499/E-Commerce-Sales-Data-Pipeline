"""Synthetic e-commerce transaction data generator.

Produces a large, *realistically messy* CSV/parquet file so the ETL pipeline
has genuine work to do. The data is deliberately not perfect: it contains
missing values, duplicated rows, invalid dates, invalid prices, missing
categories and dirty product names — exactly the kind of problems a real
business exports from its POS / e-commerce backend.

Everything is seeded so the output is fully reproducible.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PRODUCTS = [
    ("Wireless Mouse M12", "Electronics", 24.99),
    ("Mechanical Keyboard K87", "Electronics", 89.50),
    ("USB-C Hub 7-in-1", "Electronics", 45.00),
    ("LED Monitor 27in", "Electronics", 249.99),
    ("Bluetooth Headphones", "Electronics", 129.00),
    ("Noise-Cancelling Earbuds", "Electronics", 79.99),
    ("Laptop Stand Aluminum", "Office", 39.50),
    ("Desk Organizer", "Office", 18.75),
    ("Ergonomic Office Chair", "Office", 289.00),
    ("Standing Desk 120x60", "Office", 499.00),
    ("Whiteboard Marker Set", "Office", 8.99),
    ("Paper A4 Ream", "Office", 6.49),
    ("Coffee Maker 12-Cup", "Kitchen", 74.99),
    ("Blender 800W", "Kitchen", 59.99),
    ("Air Fryer 5L", "Kitchen", 129.50),
    ("Electric Kettle", "Kitchen", 34.99),
    ("Non-Stick Pan 28cm", "Kitchen", 42.00),
    ("Cutlery Set 24pc", "Kitchen", 89.99),
    ("Yoga Mat Pro", "Fitness", 32.50),
    ("Adjustable Dumbbells 25kg", "Fitness", 219.00),
    ("Resistance Bands Set", "Fitness", 24.00),
    ("Smart Fitness Watch", "Fitness", 149.00),
    ("Jump Rope Speed", "Fitness", 15.99),
    ("Water Bottle 1L", "Fitness", 12.50),
    ("HD Webcam 1080p", "Electronics", 54.99),
    ("Wireless Router AX3000", "Electronics", 139.00),
]

# Minor misspellings used to inject dirty category / product values that the
# standardisation step must clean up.
DIRTY_CATEGORIES = ["Electronics ", "elecTronics", "Office ", "Kitchen ", "Fitness "]
DIRTY_STATUSES = ["COMPLETED", "Completed", "SHIPPED", "cancelled ", " COMPLETED"]


def generate_transactions(
    n_rows: int = 100000,
    seed: int = 42,
    start: date = date(2023, 1, 1),
    end: date = date(2024, 12, 31),
) -> pd.DataFrame:
    """Generate a messy e-commerce transactions dataset.

    Args:
        n_rows: number of base rows to generate before duplicates.
        seed: random seed for reproducibility.
        start/end: date window for transactions.

    Returns:
        A pandas DataFrame with the raw, messy transaction records.
    """
    rng = random.Random(seed)
    nprng = np.random.RandomState(seed)

    products = [p[0] for p in PRODUCTS]
    prices = {p[0]: p[2] for p in PRODUCTS}
    categories = {p[0]: p[1] for p in PRODUCTS}

    order_prefix = [f"ORD{i:07d}" for i in range(1, n_rows + 1)]

    # ----- candidate synthetic rows (before deliberate errors) ---------------
    n = n_rows
    uniform = np.ones(len(products)) / len(products)
    product = nprng.choice(products, size=n, p=uniform)
    unit_price = np.array([prices[p] for p in product], dtype=float)
    quantity = nprng.choice([1, 1, 1, 2, 2, 3, 4, 5], size=n)
    category = np.array([categories[p] for p in product])

    # Dates with seasonal weighting.
    total_days = (end - start).days
    weights = np.full(total_days, 1.0)
    weights[-90:] *= 1.6
    probs = weights / weights.sum()
    day_offsets = nprng.choice(total_days, size=n, p=probs)
    dates = [
        (start + timedelta(days=int(off))).isoformat() for off in day_offsets
    ]

    customer_id = nprng.randint(1001, 1200, size=n).astype(str)

    order_id = nprng.choice(order_prefix, size=n, replace=False)
    # Sometimes a single order contains multiple distinct line items; keep the
    # natural 1 line-item-per-row model but share some order ids to create
    # multi-line orders (realistic) — by design here each order_id is unique,
    # and duplicates below simulate resubmitted exports.

    status = ["completed"] * n

    base = pd.DataFrame(
        {
            "order_id": order_id,
            "order_date": dates,
            "customer_id": customer_id,
            "product": product,
            "category": category,
            "unit_price": unit_price,
            "quantity": quantity,
            "status": status,
        }
    )

    # ----- inject realistic quality problems ---------------------------------

    # 1. ~1.5% duplicated rows (resubmitted/duplicated export lines).
    dup_count = int(n * 0.015)
    dups = base.sample(dup_count, random_state=nprng.randint(0, 1_000_000))
    base = pd.concat([base, dups], ignore_index=True)

    # 2. Dirty categorical values: some statuses and categories are messy.
    mix_rng = random.Random(seed + 1)
    dirty_idx = mix_rng.sample(
        range(len(base)), int(len(base) * 0.08)
    )
    for i in dirty_idx:
        roll = mix_rng.random()
        col = "category" if roll < 0.5 else "status"
        if col == "category":
            base.at[i, col] = mix_rng.choice(DIRTY_CATEGORIES)
        else:
            base.at[i, col] = mix_rng.choice(
                ["completed", "shipped", "CANCELLED", "pending"]
            )

    # 3. Missing values: ~3% missing unit_price, ~2% missing category,
    #    ~1.5% missing customer.
    base.loc[nprng.choice(len(base), int(len(base) * 0.03), replace=False), "unit_price"] = np.nan
    base.loc[nprng.choice(len(base), int(len(base) * 0.02), replace=False), "category"] = np.nan
    base.loc[nprng.choice(len(base), int(len(base) * 0.015), replace=False), "customer_id"] = np.nan

    # 4. Prices stored inconsistently: a ~10% subset is a currency string
    #    ("$24.99", "$1,299.00") to mimic a POS text export.
    str_price_idx = nprng.choice(len(base), int(len(base) * 0.10), replace=False)
    for i in str_price_idx:
        v = base.at[i, "unit_price"]
        if not pd.isna(v):
            base.at[i, "unit_price"] = f"${v:,.2f}"
    # A few truly malformed prices.
    for i in nprng.choice(len(base), int(len(base) * 0.004), replace=False):
        base.at[i, "unit_price"] = rng.choice(["abc", "-5", "NA", "0.05.5"])

    # 5. Invalid / future dates: ~1% of dates are clearly wrong.
    for i in nprng.choice(len(base), int(len(base) * 0.01), replace=False):
        base.at[i, "order_date"] = rng.choice(
            ["2025-13-40", "not-a-date", "2024-02-30", "31/12/2024"]
        )

    # 6. Impossible negatives / over-scale values on a small share of rows.
    for i in range(int(len(base) * 0.005)):
        r = nprng.randint(0, len(base))
        base.at[i, "quantity"] = rng.choice([-3, 0, 2500])
    for i in range(int(len(base) * 0.003)):
        r = nprng.randint(0, len(base))
        base.at[i, "unit_price"] = 999999.0

    base = base.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return base


def write_transactions(df: pd.DataFrame, out_path, fmt: str = "csv"):
    """Persist the generated raw frame.

    Raw data is stored as CSV (the messy, mixed-type output of a real POS /
    e-commerce export). Parquet is reserved for clean, typed data downstream.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "parquet":
        df.to_parquet(out_path, index=False)
    else:
        # Ensure no float formatting artifacts for the messy raw data.
        df.to_csv(out_path, index=False, encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic e-commerce data")
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/raw/transactions.csv")
    args = parser.parse_args()

    df = generate_transactions(n_rows=args.rows, seed=args.seed)
    write_transactions(df, args.out)
    print(f"Generated {len(df)} raw rows -> {args.out}")
