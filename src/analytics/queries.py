"""Executes the SQL analytics queries and returns results as DataFrames.

This module is used by the dashboard to pull prepared business metrics from
the database, but it is also useful standalone:

    from src.analytics.queries import run_all
    run_all()
"""
from __future__ import annotations

import re

import pandas as pd
from sqlalchemy import text

from src.utils.logging import get_logger

log = get_logger(__name__)


def read_queries(path=None) -> dict[str, str]:
    """Parse analytics.sql into a dict of {query_name: sql_string}."""
    path = path or (__import__("src.utils.config", fromlist=["get_paths"])
                    .get_paths().sql / "analytics.sql")
    sql = path.read_text(encoding="utf-8")

    queries: dict[str, str] = {}
    # Each query starts with a header line "-- Q<n>. <title>" and the SQL body
    # runs until the next header boundary (or end of file).
    header_re = re.compile(r"^--\s*Q(\d+)\.\s+(.+?)\s*$", re.MULTILINE)
    matches = list(header_re.finditer(sql))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sql)
        title = m.group(2).strip()
        body = sql[m.end():end]
        # Strip comment lines from the body, keep the SQL.
        clean = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("--")
        ).strip()
        if clean:
            queries[title] = clean
    return queries


def run_queries(engine) -> dict[str, pd.DataFrame]:
    """Run every analytics query and return {metric_name: DataFrame}."""
    queries = read_queries()
    results: dict[str, pd.DataFrame] = {}
    with engine.connect() as conn:
        for name, sql in queries.items():
            results[name] = pd.read_sql(text(sql), conn)
            log.info("Analytics: %s -> %s rows", name, len(results[name]))
    return results
