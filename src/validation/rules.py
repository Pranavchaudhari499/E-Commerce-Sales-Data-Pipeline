"""Data-quality rules and the data-quality report.

Every raw row is checked against a defined set of rules. Rows that fail any
hard rule are moved to a "rejected" set with a reason, while soft issues are
reported and fixed during transformation. The pipeline never silently drops
data: everything is accounted for in a data-quality report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

from src.utils.config import Dimensions
from src.utils.logging import get_logger

log = get_logger(__name__)

_DIM = Dimensions()

# Accepted date formats (Excel/POS exports use several).
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"]
_MIN_DATE = date(2020, 1, 1)
_MAX_DATE = date(2025, 12, 31)


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------
def _to_datetime(value) -> pd.Timestamp | None:
    """Try to parse a value as a date. Returns None if unparseable/out of range."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        dt = value.date()
        return value if _MIN_DATE <= dt <= _MAX_DATE else None
    if isinstance(value, datetime):
        dt = value.date()
        return pd.Timestamp(value) if _MIN_DATE <= dt <= _MAX_DATE else None
    s = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(s, fmt)
            if _MIN_DATE <= parsed.date() <= _MAX_DATE:
                return pd.Timestamp(parsed)
        except ValueError:
            continue
    return None


def _normalise_price(value) -> float | None:
    """Parse a unit price that may be a number, a '$1,234.56' string, or garbage."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if np.isnan(value):
            return None
        return float(value)
    s = str(value).strip()
    if s == "":
        return None
    s = s.replace(",", "")
    if s.startswith("$"):
        s = s[1:]
    s = s.strip()
    # Reject obvious non-numeric garbage.
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_duplicate(df: pd.DataFrame) -> pd.Series:
    """Duplicate rows (the same row repeated in the export)."""
    return df.duplicated(keep="first")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """Valid / rejected splits plus a per-issue summary."""

    valid: pd.DataFrame
    rejected: pd.DataFrame
    issue_counts: dict[str, int]
    duplicate_count: int
    missing_counts: dict[str, int]


def _missing_mask(df: pd.DataFrame) -> pd.DataFrame:
    """Boolean mask of missing values, treating blanks/NA strings as missing."""
    mask = df.isna().copy()
    for col in df.columns:
        if df[col].dtype == object:
            mask[col] |= df[col].astype(str).str.strip().isin(
                ["", "nan", "None", "NA", "N/A", "null"]
            )
    return mask


def validate(df: pd.DataFrame) -> ValidationResult:
    """Apply validation rules to the raw frame.

    Returns valid rows (with parse-ready values) and rejected rows (with a
    'rejection_reason' column). Rejected rows are counted but not loaded.
    """
    out = df.copy()

    # --- required fields ------------------------------------------------
    missing = _missing_mask(out)
    has_required_missing = missing[["order_id"]].any(axis=1)

    # --- parse / check individual fields --------------------------------
    out["_parsed_date"] = out["order_date"].map(_to_datetime)
    out["_parsed_price"] = out["unit_price"].map(_normalise_price)
    out["_parsed_qty"] = out["quantity"].astype("Int64") if "quantity" in out else None

    issues: dict[str, pd.Series] = {}
    issues["missing_order_id"] = has_required_missing
    issues["invalid_date"] = out["order_date"].notna() & out["_parsed_date"].isna()
    issues["invalid_price"] = out["unit_price"].notna() & out["_parsed_price"].isna()
    issues["missing_price"] = out["unit_price"].isna()
    issues["invalid_quantity"] = (
        (out["_parsed_qty"].astype("Float64") <= 0)
        | (out["_parsed_qty"].astype("Float64") > _DIM.max_quantity)
    )
    issues["invalid_status"] = (
        out["status"].notna()
        & ~out["status"].astype(str).str.strip().str.lower().isin(_DIM.valid_statuses | {"shipped"})
    )

    # --- combine into hard-reject mask -----------------------------------
    issues_df = pd.DataFrame(issues)
    hard = issues_df.any(axis=1)
    # Keep duplicates flagged but not auto-rejected here; they are surfaced
    # in the quality report and de-duplicated during transform.
    rejected_out = out.loc[hard].copy()
    valid = out.loc[~hard].copy()

    # Build a per-row, readable rejection reason from the active rules.
    reason_by_index = {
        idx: " | ".join(col for col in issues_df.columns if bool(issues_df.at[idx, col]))
        for idx in rejected_out.index
    }
    rejected_out["rejection_reason"] = rejected_out.index.map(reason_by_index).fillna("")

    issue_counts = {name: int(m.sum()) for name, m in issues.items()}
    duplicate_count = int(_is_duplicate(df).sum())

    # Drop internal parse helper columns from the public result.
    valid = valid.drop(columns=["_parsed_date", "_parsed_price"])
    if "_parsed_qty" in valid.columns:
        valid = valid.drop(columns=["_parsed_qty"])

    return ValidationResult(
        valid=valid,
        rejected=rejected_out,
        issue_counts=issue_counts,
        duplicate_count=duplicate_count,
        missing_counts={
            col: int(missing[col].sum()) for col in missing.columns
        },
    )


# ---------------------------------------------------------------------------
# Data-quality report
# ---------------------------------------------------------------------------
@dataclass
class QualityReport:
    """Machine + human readable summary of data quality, written to JSON."""

    total_records: int
    valid_records: int
    rejected_records: int
    duplicate_records: int
    invalid_records: int
    issue_counts: dict[str, int] = field(default_factory=dict)
    missing_counts: dict[str, int] = field(default_factory=dict)
    retained_after_dedup: int = 0

    def to_dict(self) -> dict:
        return {
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "rejected_records": self.rejected_records,
            "duplicate_records": self.duplicate_records,
            "invalid_records": self.invalid_records,
            "retained_after_dedup": self.retained_after_dedup,
            "issue_counts": self.issue_counts,
            "missing_counts": self.missing_counts,
        }
