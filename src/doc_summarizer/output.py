"""CLI-only result rendering; persisted results and Python APIs are unchanged."""

from __future__ import annotations

import json
from pathlib import PurePath
from typing import Any


def config_lines(value: Any, prefix: str = "") -> list[str]:
    """Flatten results into copyable key=value lines, preserving path separators."""
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}={{}}"]
        return [
            line
            for key, item in value.items()
            for line in config_lines(item, f"{prefix}.{key}" if prefix else key)
        ]
    if isinstance(value, list):
        if not value:
            return [f"{prefix}=[]"]
        return [
            line
            for index, item in enumerate(value)
            for line in config_lines(item, f"{prefix}[{index}]")
        ]
    if isinstance(value, PurePath):
        value = str(value)
    if isinstance(value, str):
        escapes = {code: f"\\u{code:04x}" for code in range(32)}
        escapes.update({9: r"\t", 10: r"\n", 13: r"\r", 127: r"\u007f"})
        display = value.translate(escapes)
    else:
        display = json.dumps(value, ensure_ascii=False)
    prefix = "".join(
        f"\\u{ord(char):04x}" if ord(char) < 32 or ord(char) == 127 else char for char in prefix
    )
    return [f"{prefix}={display}"]


def emit(result: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, default=str))
    else:
        print("\n".join(config_lines(result)))
