"""Transformation stage.

Takes the *validated* rows, cleans and standardises them, computes derived
fields, de-duplicates, and fans them out into a star schema (fact + dims).

Transformation responsibilities:
  - normalise dates to a single type
  - coerce numeric types (price -> float, quantity -> int)
  - standardise categories and statuses (strip, case, canonical names)
  - fill remaining missing categorical values with documented fallbacks
  - remove duplicate rows (kept for reporting, dropped from load)
  - compute calculated fields (line total = quantity * unit_price)
  - assign stable surrogate keys for dimensions
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)

_CANONICAL_CATEGORY = {"electronics": "Electronics", "office": "Office", "kitchen": "Kitchen", "fitness": "Fitness"}

# Canonical product -> category mapping (the business's product master data).
# Category is a product attribute, so a product's true category comes from
# here rather than from a possibly-corrupted per-line value.
_PRODUCT_CATEGORY: dict[str, str] = {
    "Wireless Mouse M12": "Electronics",
    "Mechanical Keyboard K87": "Electronics",
    "USB-C Hub 7-in-1": "Electronics",
    "LED Monitor 27in": "Electronics",
    "Bluetooth Headphones": "Electronics",
    "Noise-Cancelling Earbuds": "Electronics",
    "Laptop Stand Aluminum": "Office",
    "Desk Organizer": "Office",
    "Ergonomic Office Chair": "Office",
    "Standing Desk 120x60": "Office",
    "Whiteboard Marker Set": "Office",
    "Paper A4 Ream": "Office",
    "Coffee Maker 12-Cup": "Kitchen",
    "Blender 800W": "Kitchen",
    "Air Fryer 5L": "Kitchen",
    "Electric Kettle": "Kitchen",
    "Non-Stick Pan 28cm": "Kitchen",
    "Cutlery Set 24pc": "Kitchen",
    "Yoga Mat Pro": "Fitness",
    "Adjustable Dumbbells 25kg": "Fitness",
    "Resistance Bands Set": "Fitness",
    "Smart Fitness Watch": "Fitness",
    "Jump Rope Speed": "Fitness",
    "Water Bottle 1L": "Fitness",
    "HD Webcam 1080p": "Electronics",
    "Wireless Router AX3000": "Electronics",
}


@dataclass
class TransformedData:
    """Output of the transformation stage (separate dims + fact)."""

    dim_product: pd.DataFrame
    dim_customer: pd.DataFrame
    dim_date: pd.DataFrame
    fact_sales: pd.DataFrame
    dropped_duplicates: int
    filled_missing: dict[str, int]


def _parse_price_series(s: pd.Series) -> pd.Series:
    """Parse a price column that may hold floats or '$1,234.56' strings."""
    def _parse(v):
        if pd.isna(v):
            return pd.NA
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        t = str(v).strip()
        if t == "":
            return pd.NA
        t = t.replace(",", "")
        if t.startswith("$"):
            t = t[1:]
        try:
            if re.fullmatch(r"-?\d+(\.\d+)?", t):
                return float(t)
        except ValueError:
            pass
        return pd.NA
    return s.map(_parse)


def _standardise_status(series: pd.Series) -> pd.Series:
    def _norm(v):
        s = str(v).strip().lower()
        if s in {"completed", "shipped"}:
            return "completed"
        if s == "pending":
            return "pending"
        if s in {"cancelled", "canceled"}:
            return "cancelled"
        if s == "refunded":
            return "refunded"
        return "completed"  # default
    return series.map(_norm)


def _fill_missing(df: pd.DataFrame, cols: dict[str, str]) -> dict[str, int]:
    """Fill NaN in the given columns with a constant; return counts filled."""
    filled: dict[str, int] = {}
    for col, fill_val in cols.items():
        if col in df.columns:
            mask = df[col].isna() | df[col].astype(str).str.strip().eq("")
            filled[col] = int(mask.sum())
            df.loc[mask, col] = fill_val
    return filled


def _build_date_dim(df: pd.DataFrame) -> pd.DataFrame:
    """Build dim_date from the unique dates present in the sales data."""
    dates = pd.Series(pd.to_datetime(df["order_date"]).dt.normalize().unique())
    dim = pd.DataFrame({"date": dates.dt.strftime("%Y-%m-%d")})
    dim["date_id"] = dates.dt.strftime("%Y%m%d").astype(int)
    dim["year"] = dates.dt.year
    dim["month"] = dates.dt.month
    dim["day"] = dates.dt.day
    dim["quarter"] = dates.dt.quarter
    dim["month_name"] = dates.dt.month_name()
    dim["weekday_name"] = dates.dt.day_name()
    dim["is_weekend"] = dates.dt.dayofweek.isin([5, 6]).astype(int)
    return dim[["date_id", "date", "year", "month", "day", "quarter",
                "month_name", "weekday_name", "is_weekend"]].sort_values("date")


def _build_customer_dim(df: pd.DataFrame) -> pd.DataFrame:
    """Build dim_customer from distinct customer ids (drawn from a customer catalog)."""
    from src.transform.customer_catalog import CUSTOMERS

    ids = df["customer_id"].dropna().unique().astype(int)
    rows = []
    for cid in sorted(ids):
        name, segment, city, region = CUSTOMERS.get(int(cid), (f"Customer {cid}", "Standard", "Unknown", "Unknown"))
        rows.append(
            {"customer_id": int(cid), "customer_name": name,
             "segment": segment, "city": city, "region": region}
        )
    dim = pd.DataFrame(rows, columns=[
        "customer_id", "customer_name", "segment", "city", "region"])
    return dim


def _build_product_dim(df: pd.DataFrame) -> pd.DataFrame:
    """Build dim_product from distinct products.

    The category is taken from the product master catalogue (a product's
    category is an attribute of the product, not the line item), so the
    dimension stays clean even when source rows carry corrupted categories.
    """
    names = pd.unique(df["product"].dropna().astype(str).str.strip())
    rows = [
        {"product": name, "category": _PRODUCT_CATEGORY.get(name, "Other")}
        for name in names
    ]
    frame = pd.DataFrame(rows, columns=["product", "category"])
    frame["product_id"] = range(1, len(frame) + 1)
    return frame[["product_id", "product", "category"]]


def transform(df: pd.DataFrame) -> TransformedData:
    """Clean and reshape the validated data into star-schema tables.

    Args:
        df: the *validated* rows (already passed hard validation rules).

    Returns:
        TransformedData with dimension frames and a fact frame.
    """
    t = df.copy()

    # ----- de-duplicate (same row repeated in the export) ---------------
    dup_mask = t.duplicated(keep="first")
    dropped_duplicates = int(dup_mask.sum())
    t = t.loc[~dup_mask].copy()
    log.info("Dropped %s duplicate rows", dropped_duplicates)

    # ----- coerce and clean fields --------------------------------------
    t["unit_price"] = _parse_price_series(t["unit_price"])
    t["order_date"] = pd.to_datetime(
        t["order_date"].astype(str).map(
            lambda s: _normalise_date_str(s)
        ), errors="coerce"
    )
    t["quantity"] = pd.to_numeric(t["quantity"], errors="coerce").astype("Int64")
    # Category is a product attribute: take it from the product master so a
    # per-line corrupted category cannot fragment the product dimension.
    t["category"] = t["product"].map(
        lambda p: _PRODUCT_CATEGORY.get(str(p).strip(), "Other")
    )
    t["status"] = _standardise_status(t["status"])

    # ----- fill remaining missing values with documented fallbacks ------
    filled = _fill_missing(
        t,
        {
            "customer_id": "0",
            "unit_price": 0.0,
            "quantity": 1,
            "product": "Unknown Product",
        },
    )

    # --- validate price again after fill: drop rows with no usable price ----
    t = t[t["unit_price"].notna() & (t["unit_price"] >= 0) & (t["unit_price"] <= 10000)]
    t = t[t["quantity"].notna()]

    # ----- calculated field ---------------------------------------------
    t["line_total"] = (t["quantity"] * t["unit_price"]).round(2)
    t["revenue_flag"] = t["status"].isin(["completed", "shipped"]).astype(int)

    t["customer_id"] = t["customer_id"].astype(int)
    t["order_id"] = t["order_id"].astype(str).str.strip()
    t["product"] = t["product"].astype(str).str.strip()

    # ----- build dimension tables ---------------------------------------
    dim_date = _build_date_dim(t)
    dim_customer = _build_customer_dim(t)
    dim_product = _build_product_dim(t)

    # Normalise order_date to an ISO date string so it lines up with dim_date.
    t["date"] = t["order_date"].dt.strftime("%Y-%m-%d")

    # attach surrogate keys to the fact rows
    t = t.merge(dim_date[["date_id", "date"]], on="date", how="left")
    t = t.merge(dim_customer, on="customer_id", how="left")
    t = t.merge(dim_product, on=["product", "category"], how="left")

    fact = t[
        ["order_id", "quantity", "unit_price", "line_total",
         "status", "revenue_flag", "customer_id", "date_id", "product_id"]
    ].copy()
    fact["sale_id"] = range(1, len(fact) + 1)
    fact = fact[
        ["sale_id", "order_id", "date_id", "customer_id", "product_id",
         "quantity", "unit_price", "line_total", "status", "revenue_flag"]
    ]

    return TransformedData(
        dim_product=dim_product,
        dim_customer=dim_customer,
        dim_date=dim_date,
        fact_sales=fact,
        dropped_duplicates=dropped_duplicates,
        filled_missing=filled,
    )


def _normalise_date_str(value: str) -> str:
    """Normalise a date string into YYYY-MM-DD for pd.to_datetime.

    Handles dd/mm/yyyy vs mm/dd/yyyy ambiguity; we assume EU order (dd/mm/yyyy)
    for slashes where both parts are <= 12 and unambiguous by digit count.
    """
    s = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y%m%d"):
        try:
            return pd.to_datetime(s, format=fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", s):
        parts = re.split(r"[/-]", s)
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        if m > 12:  # clearly day/month swapped -> treat first as month
            m, d = d, m
        try:
            return pd.Timestamp(year=y, month=m, day=d).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return s
