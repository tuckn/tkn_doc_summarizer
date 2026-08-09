"""Resolve file or URL inputs to immutable local document content."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

from doc_summarizer.io import sha256_bytes
from doc_summarizer.models import DocumentSource

logger = logging.getLogger(__name__)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n")
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter closing delimiter is missing")
    try:
        metadata = yaml.safe_load(normalized[4:end])
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a mapping")
    return dict(metadata), normalized[end + 5 :]


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must use http or https")
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_items = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((parsed.scheme.lower(), host, path, query, ""))


def _is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _read_source(path: Path, max_input_bytes: int) -> DocumentSource:
    expanded = path.expanduser()
    absolute = expanded if expanded.is_absolute() else (Path.cwd() / expanded)
    absolute = absolute.absolute()
    if not absolute.exists():
        raise ValueError(f"source file does not exist: {path}")
    if not absolute.is_file():
        raise ValueError(f"source is not a file: {absolute}")
    try:
        payload = absolute.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read source file {absolute}: {exc}") from exc
    if len(payload) > max_input_bytes:
        raise ValueError(
            f"source file exceeds max_input_bytes ({len(payload)} > {max_input_bytes}): {absolute}"
        )
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"source file must be UTF-8: {absolute}: {exc}") from exc
    metadata, body = split_frontmatter(text)
    content = body.strip()
    if not content:
        raise ValueError(f"source content is empty: {absolute}")
    title = str(metadata.get("title") or "").strip()
    if not title:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", content)
        title = match.group(1).strip() if match else absolute.stem
    url_value = str(metadata.get("url") or "").strip() or None
    cover_value = str(metadata.get("cover") or "").strip() or None
    published_value = metadata.get("published") or metadata.get("date")
    return DocumentSource(
        path=absolute,
        title=title,
        url=url_value,
        cover=cover_value,
        published=str(published_value) if published_value else None,
        content=content,
        source_sha256=sha256_bytes(payload),
        source_size_bytes=len(payload),
    )


def _find_url_source(url: str, roots: list[Path], max_input_bytes: int) -> DocumentSource:
    if not roots:
        raise ValueError(
            "URL input requires at least one source_roots entry; "
            "clip the article first or pass its local file path"
        )
    wanted = normalize_url(url)
    matches: list[Path] = []
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"configured source root does not exist: {root}")
        logger.debug("Searching source root: %s", root)
        for candidate in root.rglob("*.md"):
            try:
                text = candidate.read_text(encoding="utf-8-sig")
                metadata, _ = split_frontmatter(text)
                candidate_url = str(metadata.get("url") or "").strip()
                if metadata.get("cliptool") == "Codex" or not candidate_url:
                    continue
                if normalize_url(candidate_url) == wanted:
                    matches.append(candidate)
            except (OSError, UnicodeError, ValueError):
                logger.debug("Skipping unreadable source candidate: %s", candidate)
    if not matches:
        raise ValueError(
            "no clipped Markdown source matched the URL; "
            "create it with Obsidian Web Clipper or pass a file path"
        )
    unique_by_path = {str(path.absolute()).casefold(): path.absolute() for path in matches}
    unique = sorted(unique_by_path.values())
    if len(unique) > 1:
        joined = ", ".join(str(path) for path in unique)
        raise ValueError(f"multiple clipped Markdown files match the URL: {joined}")
    return _read_source(unique[0], max_input_bytes)


def resolve_source(
    value: str,
    *,
    source_roots: list[Path],
    max_input_bytes: int,
) -> DocumentSource:
    if _is_url(value):
        logger.info("Resolving URL from clipped Markdown")
        return _find_url_source(value, source_roots, max_input_bytes)
    logger.info("Reading local source document: %s", value)
    return _read_source(Path(value), max_input_bytes)
