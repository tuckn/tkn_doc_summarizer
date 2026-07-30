"""Console logging shared by the command-line interface."""

from __future__ import annotations

import ctypes
import logging
import os
from collections.abc import Mapping
from typing import Any, TextIO

SUCCESS = 25
logging.addLevelName(SUCCESS, "SUCCESS")

_RESET = "\x1b[0m"
_LEVEL_COLORS: Mapping[int, str] = {
    SUCCESS: "\x1b[32m",
    logging.ERROR: "\x1b[31m",
    logging.CRITICAL: "\x1b[31m",
}


def log_success(logger: logging.Logger, message: str, *args: Any) -> None:
    logger.log(SUCCESS, message, *args)


def _enable_windows_virtual_terminal(stream: TextIO) -> bool:
    if os.name != "nt":
        return True
    try:
        import msvcrt
        from ctypes import wintypes

        handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleMode.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetConsoleMode.restype = wintypes.BOOL
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetConsoleMode.restype = wintypes.BOOL
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enabled = 0x0004
        if mode.value & enabled:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | enabled))
    except (AttributeError, OSError, ValueError):
        return False


def supports_color(stream: TextIO) -> bool:
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    try:
        if not stream.isatty():
            return False
    except (AttributeError, OSError):
        return False
    return _enable_windows_virtual_terminal(stream)


class ColorFormatter(logging.Formatter):
    def __init__(self, fmt: str, *, use_color: bool) -> None:
        super().__init__(fmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        color = _LEVEL_COLORS.get(record.levelno) if self.use_color else None
        return f"{color}{rendered}{_RESET}" if color else rendered
