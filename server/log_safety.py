"""Quita saltos de línea de todo lo que se escribe en el log."""
from __future__ import annotations

import logging


def strip_log_breaks(value):
    if isinstance(value, str):
        return value.replace("\r", " ").replace("\n", " ")
    return value


class LogSanitizerFilter(logging.Filter):
    """Helper central: ningún argumento de log conserva CR o LF."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = strip_log_breaks(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: strip_log_breaks(val) for key, val in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(strip_log_breaks(item) for item in record.args)
        return True


def install_log_sanitizer(target: logging.Logger | None = None) -> None:
    sanitizer = LogSanitizerFilter()
    root = logging.getLogger()
    if not any(isinstance(item, LogSanitizerFilter) for item in root.filters):
        root.addFilter(sanitizer)
    if target is not None and not any(isinstance(item, LogSanitizerFilter) for item in target.filters):
        target.addFilter(sanitizer)
