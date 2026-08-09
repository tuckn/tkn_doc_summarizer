"""Portable output naming and file URI helpers."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path

INVALID = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
)


def sanitize_title(title: str) -> str:
    visible = "".join(character for character in title if ord(character) >= 32)
    return re.sub(r"\s+", " ", visible.translate(INVALID)).strip(" .")


def _source_date(value: str | None, source_path: Path) -> date:
    if value:
        raw = value.strip()
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                return date.fromisoformat(raw)
            normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            pass
    match = re.match(r"^(\d{4})(\d{2})(\d{2})", source_path.stem)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return datetime.now().astimezone().date()


def build_output_path(
    output_root: Path,
    *,
    source_path: Path,
    published: str | None,
    title: str,
    profile_name: str,
    prompt_id: str,
    identity_suffix: str | None = None,
    limit: int = 200,
) -> Path:
    source_date = _source_date(published, source_path)
    prefix = source_date.strftime("%Y%m%d")
    identity = f"_{identity_suffix}" if identity_suffix else ""
    suffix = f"{identity}_{profile_name}_{uuid.UUID(prompt_id).hex[:8]}.md"
    safe = sanitize_title(title)
    if not safe:
        raise ValueError("title is empty after filename sanitization")
    budget = limit - len(f"{prefix}_{suffix}".encode())
    shortened = ""
    for character in safe:
        if len((shortened + character).encode("utf-8")) > budget:
            break
        shortened += character
    shortened = shortened.rstrip(" .")
    if not shortened:
        raise ValueError("title is too long to build a portable filename")
    filename = f"{prefix}_{shortened}{suffix}"
    return output_root / str(source_date.year) / filename
