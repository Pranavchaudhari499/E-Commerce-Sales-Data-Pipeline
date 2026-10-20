"""The ETL pipeline orchestrator.

Wires together the extract, validate, transform and load stages, generates a
data-quality report, and enforces robust error handling + execution auditing.

Architecture:
    EXTRACT -> VALIDATE -> TRANSFORM -> LOAD -> QUALITY REPORT
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

from src.extract.extract import extract as run_extract
from src.load.load import get_engine, load as run_load
from src.transform.transform import transform as run_transform
from src.utils.config import get_paths
from src.utils.logging import get_logger, setup_logging
from src.validation.quality import write_quality_report
from src.validation.rules import QualityReport, validate

log = get_logger(__name__)


@dataclass
class PipelineResult:
    """Outcome summary returned to callers."""

    extract_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    loaded_rows: dict
    rejected_file: str | None
    quality_report: str
    duration_seconds: float
    success: bool


def _save_rejected(rejected: pd.DataFrame, path) -> str:
    path = get_paths().data_quality / path
    path.parent.mkdir(parents=True, exist_ok=True)
    rejected.to_csv(path, index=False, encoding="utf-8")
    return str(path)


def run_pipeline(
    extract_path=None,
    db_engine: str | None = None,
) -> PipelineResult:
    """Execute the full ETL pipeline.

    Args:
        extract_path: optional explicit path to the raw source file.
        db_engine: optional override ('sqlite' | 'postgresql').

    Returns:
        PipelineResult summarising every stage and where outputs were written.
    """
    start = time.time()

    if db_engine:
        import os

        os.environ["DB_ENGINE"] = db_engine

    try:
        # 1. EXTRACT -----------------------------------------------------
        log.info("=== STAGE 1/5: EXTRACT ===")
        extracted = run_extract(extract_path)
        extract_rows = extracted.row_count

        # 2. VALIDATE ----------------------------------------------------
        log.info("=== STAGE 2/5: VALIDATE ===")
        validation = validate(extracted.df)
        rejected_file = _save_rejected(
            validation.rejected, "rejected_records.csv"
        )
        log.info(
            "Validation: %s valid, %s rejected, %s duplicates",
            len(validation.valid),
            len(validation.rejected),
            validation.duplicate_count,
        )

        # 3. TRANSFORM ---------------------------------------------------
        log.info("=== STAGE 3/5: TRANSFORM ===")
        transformed = run_transform(validation.valid)
        log.info(
            "Transform complete: %s fact rows, %s products, %s customers, %s dates",
            len(transformed.fact_sales),
            len(transformed.dim_product),
            len(transformed.dim_customer),
            len(transformed.dim_date),
        )

        # 4. LOAD --------------------------------------------------------
        log.info("=== STAGE 4/5: LOAD ===")
        engine = get_engine()
        loaded = run_load(transformed, engine)

        # 5. QUALITY REPORT ----------------------------------------------
        log.info("=== STAGE 5/5: QUALITY REPORT ===")
        report = QualityReport(
            total_records=extract_rows,
            valid_records=len(validation.valid),
            rejected_records=len(validation.rejected),
            duplicate_records=validation.duplicate_count,
            invalid_records=sum(validation.issue_counts.values()),
            issue_counts=validation.issue_counts,
            missing_counts=validation.missing_counts,
        )
        paths = write_quality_report(report, get_paths().data_quality)

        duration = round(time.time() - start, 2)
        result = PipelineResult(
            extract_rows=extract_rows,
            valid_rows=len(validation.valid),
            rejected_rows=len(validation.rejected),
            duplicate_rows=validation.duplicate_count,
            loaded_rows=loaded,
            rejected_file=rejected_file,
            quality_report=str(paths["markdown"]),
            duration_seconds=duration,
            success=True,
        )
        log.info(
            "Pipeline complete in %ss — loaded %s rows",
            duration,
            sum(loaded.values()),
        )
        return result

    except Exception as exc:  # noqa: BLE001 — pipeline must not die silently
        log.exception("Pipeline FAILED: %s", exc)
        raise
