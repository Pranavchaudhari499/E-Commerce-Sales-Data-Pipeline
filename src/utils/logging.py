"""Logging setup shared across the pipeline.

A single configured logger plus a file/console handler keeps logs consistent
and greppable. In a production deployment the file handler would point at a
dedicated log directory and could be picked up by a log aggregator.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    """Configure root logging. Safe to call multiple times.

    Args:
        level: logging level for the console handler.
        log_file: optional path to also write logs to disk.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers when called more than once.
    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(console)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if not any(
            getattr(h, "baseFilename", None) == str(log_file)
            for h in root.handlers
        ):
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(_FORMAT))
            root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
