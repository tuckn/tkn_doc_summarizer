"""Read an ordered, local UTF-8 source list without shell parsing."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

MAX_SOURCE_LIST_BYTES = 2_000_000


def read_source_list(path: Path) -> list[str]:
    """Resolve relative files against the list's directory; retain URL search keys."""
    path = path.expanduser().absolute()
    with path.open("rb") as stream:
        payload = stream.read(MAX_SOURCE_LIST_BYTES + 1)
    if len(payload) > MAX_SOURCE_LIST_BYTES:
        raise ValueError(f"source list exceeds {MAX_SOURCE_LIST_BYTES} bytes: {path}")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"source list must be UTF-8: {path}") from exc
    sources: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if any(ord(char) < 32 for char in value):
            raise ValueError(f"source list contains a control character: {path}:{number}")
        if value.startswith(('"', "'")):
            raise ValueError(f"source list paths must not be quoted: {path}:{number}")
        if urlparse(value).scheme.lower() not in {"http", "https"}:
            source = Path(value).expanduser()
            if not source.is_absolute():
                source = path.parent / source
            value = str(source.absolute())
        sources.append(value)
    if not sources:
        raise ValueError(f"source list contains no sources: {path}")
    return sources
