"""Dashboard data-access layer.

Separates DB queries from the Dash UI layer so they are easy to test and
reuse. All queries return pandas DataFrames with stable columns.

Filters (region / category / date) are applied at the **SQL level** so the
dashboard stays efficient as the dataset grows — we never pull the whole table
into Python just to slice it.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text

from src.load.load import get_engine
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class Filters:
    """Dashboard filter state, applied as SQL WHERE clauses."""

    region: str = "All"
    category: str = "All"
    start_date: str | None = None
    end_date: str | None = None

    def has_conditions(self) -> bool:
        return bool(self.conditions())

    def conditions(self) -> list[str]:
        conds = []
        if self.region not in (None, "", "All"):
            conds.append("c.region = :region")
        if self.category not in (None, "", "All"):
            conds.append("p.category = :category")
        if self.start_date:
            conds.append("d.date >= :start_date")
        if self.end_date:
            conds.append("d.date <= :end_date")
        return conds

    def params(self) -> dict:
        return {
            "region": self.region,
            "category": self.category,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    def where_sql(self, *, has_revenue_flag: bool) -> str:
        """Render the WHERE fragment.

        Args:
            has_revenue_flag: True if the base query already contains
                `WHERE f.revenue_flag = 1`, in which case filter conditions are
                appended with `AND`. Otherwise they start a fresh `WHERE`.
        """
        conds = self.conditions()
        if not conds:
            return ""
        clause = " AND ".join(conds)
        return f"AND {clause}" if has_revenue_flag else f"WHERE {clause}"


def _exclude_unknown(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Filter out the 'Unknown' fallback rows from geographic/category views."""
    if group_col in df.columns:
        return df[~df[group_col].astype(str).eq("Unknown")]
    return df


# ---------------------------------------------------------------------------
# Filter-aware SQL templates.
#   {where}         -> rendered WHERE fragment ("" when no filters)
#   fact/dims the where clause references (c=dim_customer, p=dim_product,
#   d=dim_date) are always joined in each query.
# ---------------------------------------------------------------------------
_SQL = {
    "kpis": """
        SELECT
            COUNT(DISTINCT f.order_id) AS total_orders,
            SUM(CASE WHEN f.revenue_flag = 1 THEN f.quantity ELSE 0 END) AS units_sold,
            ROUND(SUM(CASE WHEN f.revenue_flag = 1 THEN f.line_total ELSE 0 END), 2) AS total_revenue,
            ROUND(
                SUM(CASE WHEN f.revenue_flag = 1 THEN f.line_total ELSE 0 END)
                / NULLIF(COUNT(DISTINCT CASE WHEN f.revenue_flag = 1 THEN f.order_id END), 0),
                2
            ) AS average_order_value
        FROM fact_sales f
        JOIN dim_customer c ON f.customer_id = c.customer_id
        JOIN dim_product  p ON f.product_id  = p.product_id
        JOIN dim_date     d ON f.date_id     = d.date_id
        {where}
    """,
    "revenue_by_month": """
        SELECT
            d.year, d.month, d.month_name,
            ROUND(SUM(f.line_total), 2) AS revenue,
            COUNT(DISTINCT f.order_id)  AS orders
        FROM fact_sales f
        JOIN dim_date     d ON f.date_id     = d.date_id
        JOIN dim_customer c ON f.customer_id = c.customer_id
        JOIN dim_product  p ON f.product_id  = p.product_id
        WHERE f.revenue_flag = 1 {where}
        GROUP BY d.year, d.month, d.month_name
        ORDER BY d.year, d.month
    """,
    "revenue_by_category": """
        SELECT
            p.category,
            ROUND(SUM(f.line_total), 2) AS revenue,
            COUNT(DISTINCT f.order_id)  AS orders
        FROM fact_sales f
        JOIN dim_product  p ON f.product_id  = p.product_id
        JOIN dim_customer c ON f.customer_id = c.customer_id
        JOIN dim_date     d ON f.date_id     = d.date_id
        WHERE f.revenue_flag = 1 {where}
        GROUP BY p.category
        ORDER BY revenue DESC
    """,
    "top_products": """
        SELECT
            p.product,
            p.category,
            ROUND(SUM(f.line_total), 2) AS revenue,
            SUM(f.quantity)             AS units
        FROM fact_sales f
        JOIN dim_product  p ON f.product_id  = p.product_id
        JOIN dim_customer c ON f.customer_id = c.customer_id
        JOIN dim_date     d ON f.date_id     = d.date_id
        WHERE f.revenue_flag = 1 {where}
        GROUP BY p.product_id, p.product, p.category
        ORDER BY revenue DESC
        LIMIT :limit
    """,
    "revenue_by_region": """
        SELECT
            c.region,
            ROUND(SUM(f.line_total), 2) AS revenue,
            COUNT(DISTINCT f.order_id)  AS orders
        FROM fact_sales f
        JOIN dim_customer c ON f.customer_id = c.customer_id
        JOIN dim_product  p ON f.product_id  = p.product_id
        JOIN dim_date     d ON f.date_id     = d.date_id
        WHERE f.revenue_flag = 1 {where}
        GROUP BY c.region
        ORDER BY revenue DESC
    """,
    "segments": """
        SELECT
            c.segment,
            COUNT(DISTINCT f.customer_id) AS customers,
            ROUND(SUM(f.line_total), 2)   AS revenue
        FROM fact_sales f
        JOIN dim_customer c ON f.customer_id = c.customer_id
        JOIN dim_product  p ON f.product_id  = p.product_id
        JOIN dim_date     d ON f.date_id     = d.date_id
        WHERE f.revenue_flag = 1 {where}
        GROUP BY c.segment
        ORDER BY revenue DESC
    """,
    "transactions": """
        SELECT
            d.date                             AS order_date,
            f.order_id,
            c.customer_name,
            c.segment,
            p.category,
            p.product,
            f.quantity,
            f.unit_price,
            f.line_total,
            f.status
        FROM fact_sales f
        JOIN dim_date     d ON f.date_id     = d.date_id
        JOIN dim_customer c ON f.customer_id = c.customer_id
        JOIN dim_product  p ON f.product_id  = p.product_id
        {where}
        ORDER BY d.date DESC, f.order_id
        LIMIT :limit
    """,
}

# Queries that already hard-code `WHERE f.revenue_flag = 1` (filters add AND).
_HAS_REVENUE_FLAG = {"revenue_by_month", "revenue_by_category", "top_products",
                     "revenue_by_region", "segments"}


def _apply(name: str, f: Filters, extra: dict | None = None) -> pd.DataFrame:
    sql = _SQL[name].format(
        where=f.where_sql(has_revenue_flag=(name in _HAS_REVENUE_FLAG))
    )
    params = dict(f.params()) if f.has_conditions() else {}
    if extra:
        params.update(extra)
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or None)


def kpis(f: Filters | None = None) -> pd.DataFrame:
    """Executive KPI summary (revenue, orders, units, AOV)."""
    return _apply("kpis", f or Filters())


def revenue_by_month(f: Filters | None = None) -> pd.DataFrame:
    return _apply("revenue_by_month", f or Filters())


def revenue_by_category(f: Filters | None = None) -> pd.DataFrame:
    return _apply("revenue_by_category", f or Filters())


def top_products(f: Filters | None = None, limit: int = 10) -> pd.DataFrame:
    return _apply("top_products", f or Filters(), {"limit": limit})


def revenue_by_region(f: Filters | None = None) -> pd.DataFrame:
    return _exclude_unknown(_apply("revenue_by_region", f or Filters()), "region")


def segments(f: Filters | None = None) -> pd.DataFrame:
    return _exclude_unknown(_apply("segments", f or Filters()), "segment")


def transaction_table(f: Filters | None = None, limit: int = 500) -> pd.DataFrame:
    return _apply("transactions", f or Filters(), {"limit": limit})
