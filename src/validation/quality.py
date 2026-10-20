"""Write the data-quality report to disk (JSON + human-readable text)."""
from __future__ import annotations

import json
from pathlib import Path

from src.validation.rules import QualityReport
from src.utils.logging import get_logger

log = get_logger(__name__)


def write_quality_report(report: QualityReport, out_dir: Path) -> dict[str, Path]:
    """Persist the report as JSON plus a readable markdown summary.

    Returns a dict mapping format -> file path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "quality_report.json"
    md_path = out_dir / "quality_report.md"

    json_path.write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )
    md_path.write_text(_to_markdown(report), encoding="utf-8")

    log.info("Quality report written to %s and %s", json_path, md_path)
    return {"json": json_path, "markdown": md_path}


def _to_markdown(report: QualityReport) -> str:
    """Render the quality report as a readable Markdown summary."""
    lines = []
    lines.append("# Pipeline Data-Quality Report")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Total records read | {report.total_records} |")
    lines.append(f"| Valid records (loaded) | {report.valid_records} |")
    lines.append(f"| Rejected records | {report.rejected_records} |")
    lines.append(f"| Duplicate records removed | {report.duplicate_records} |")
    lines.append(
        f"| Invalid records (failed a rule) | {report.invalid_records} |"
    )
    lines.append("")
    lines.append("## Issues detected by rule")
    lines.append("")
    lines.append("| Rule | Count |")
    lines.append("|---|---|")
    for rule, count in report.issue_counts.items():
        lines.append(f"| {rule} | {count} |")
    lines.append("")
    lines.append("## Missing values per column")
    lines.append("")
    lines.append("| Column | Missing count |")
    lines.append("|---|---|")
    for col, count in report.missing_counts.items():
        lines.append(f"| {col} | {count} |")
    lines.append("")
    return "\n".join(lines)
