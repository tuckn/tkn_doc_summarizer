"""Per-run supplementary context, kept separate from source documents."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from doc_summarizer.io import sha256_bytes

_PATH_PREFIX = re.compile(r"^(?:[A-Za-z]:|[\\/]|~(?:[\\/]|$)|\.{1,2}[\\/])")
_PATH_SUFFIX = re.compile(r'^[^\s<>:"|?*]+\.[A-Za-z][A-Za-z0-9]{0,15}$')
_RELATIVE_PATH = re.compile(r'^[^\s<>:"|?*]+[\\/][^\s<>:"|?*]+$')
_URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _context_path(value: str) -> Path | None:
    if "\n" in value or "\r" in value or _URI.match(value):
        return None
    if (
        _PATH_PREFIX.match(value)
        or _PATH_SUFFIX.fullmatch(value)
        or _RELATIVE_PATH.fullmatch(value)
    ):
        return Path(value).expanduser()
    # Plain text can contain characters or lengths that no local filename supports.
    if len(value) > 255 or any(ord(char) < 32 or char in '<>:"|?*' for char in value):
        return None
    source = Path(value)
    try:
        source.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"cannot inspect --context file {source}: {exc}") from exc
    return source


def _read_context_file(source: Path, max_input_bytes: int) -> str:
    try:
        if not stat.S_ISREG(source.stat().st_mode):
            raise ValueError(f"--context path is not a regular file: {source}")
        with source.open("rb") as stream:
            payload = stream.read(max_input_bytes + 1)
    except OSError as exc:
        raise ValueError(f"cannot read --context file {source}: {exc}") from exc
    if len(payload) > max_input_bytes:
        raise ValueError("--context file exceeds max_input_bytes")
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("--context file must be UTF-8 text") from exc


def load_context(
    values: str | list[str] | None,
    *,
    max_input_bytes: int,
) -> str | None:
    inputs = [values] if isinstance(values, str) else values or []
    parts: list[str] = []
    total_bytes = 0
    for value in inputs:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("--context must not be empty")
        source = _context_path(clean_value)
        text = _read_context_file(source, max_input_bytes) if source is not None else clean_value
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("--context must not be empty")
        total_bytes += len(normalized.encode("utf-8")) + (2 if parts else 0)
        if total_bytes > max_input_bytes:
            raise ValueError("combined context exceeds max_input_bytes")
        parts.append(normalized)
    return "\n\n".join(parts) or None


def context_sha256(context: str | None) -> str | None:
    return sha256_bytes(context.encode("utf-8")) if context is not None else None
