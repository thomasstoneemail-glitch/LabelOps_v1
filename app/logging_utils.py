"""Utilities for centralized logging with redaction helpers."""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Optional

_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
_LONG_DIGITS_RE = re.compile(r"\b\d{5,}\b")


class _UtcFormatter(logging.Formatter):
    """Formatter that emits UTC timestamps in ISO-8601 format."""

    converter = staticmethod(__import__("time").gmtime)


def setup_logging(log_dir: str, level: str = "INFO") -> logging.Logger:
    """Configure root logging to console and a rotating file handler.

    Args:
        log_dir: Directory to store log files.
        level: Logging level name (e.g., "INFO").

    Returns:
        Configured root logger.
    """
    if not log_dir:
        raise ValueError("log_dir must be provided")

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "labelops.log")

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)

    formatter = _UtcFormatter(
        fmt="%(asctime)sZ %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.debug("Logging initialized", extra={"log_path": log_path})
    return logger


def redact(s: Optional[str]) -> str:
    """Redact potentially sensitive information from a string.

    This replaces postcodes and long digit sequences, and limits length.
    """
    if not s:
        return ""

    sanitized = str(s)
    sanitized = _POSTCODE_RE.sub("POSTCODE", sanitized)
    sanitized = _LONG_DIGITS_RE.sub("NUM", sanitized)

    max_len = 200
    if len(sanitized) > max_len:
        return f"{sanitized[:max_len]}…"
    return sanitized


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name."""
    if not name:
        raise ValueError("name must be provided")
    return logging.getLogger(name)
