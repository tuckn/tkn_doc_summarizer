from __future__ import annotations

import logging

from doc_summarizer.console_logging import SUCCESS, ColorFormatter


def _record(level: int) -> logging.LogRecord:
    return logging.LogRecord("test", level, "", 0, "message", (), None)


def test_success_level_order() -> None:
    assert logging.INFO < SUCCESS < logging.WARNING
    assert logging.getLevelName(SUCCESS) == "SUCCESS"


def test_color_formatter_colors_success_and_error() -> None:
    formatter = ColorFormatter("[%(levelname)s] %(message)s", use_color=True)
    assert formatter.format(_record(SUCCESS)).startswith("\x1b[32m[SUCCESS]")
    assert formatter.format(_record(logging.ERROR)).startswith("\x1b[31m[ERROR]")


def test_color_formatter_is_plain_when_disabled() -> None:
    formatter = ColorFormatter("[%(levelname)s] %(message)s", use_color=False)
    assert formatter.format(_record(logging.INFO)) == "[INFO] message"
