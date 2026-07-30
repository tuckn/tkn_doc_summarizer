"""Deterministic validation for generated summary notes."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from doc_summarizer.io import sha256_bytes
from doc_summarizer.notes import (
    REVIEW_STATUSES,
    SUMMARY_SCHEMA_VERSION,
    file_uri_to_path,
)
from doc_summarizer.source import split_frontmatter

SUMMARY_FRONTMATTER_ORDER = [
    "type",
    "schemaVersion",
    "title",
    "description",
    "cover",
    "nouns",
    "url",
    "cliptool",
    "source",
    "sourceSha256",
    "generator",
    "requestedModel",
    "promptId",
    "promptVersion",
    "promptSha256",
    "promptEnvelopeVersion",
    "reviewStatus",
    "date",
    "updated",
    "noteId",
]


def _frontmatter_keys(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n")
    end = normalized.find("\n---\n", 4)
    if not normalized.startswith("---\n") or end < 0:
        return []
    keys: list[str] = []
    for line in normalized[4:end].splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9]*):", line)
        if match:
            keys.append(match.group(1))
    return keys


def _section(body: str, heading: str, next_heading: str | None = None) -> str:
    start_match = re.search(rf"(?m)^{re.escape(heading)}\s*$", body)
    if not start_match:
        raise ValueError(f"summary note has no {heading} heading")
    start = start_match.end()
    end = len(body)
    if next_heading:
        end_match = re.search(rf"(?m)^{re.escape(next_heading)}\s*$", body[start:])
        if not end_match:
            raise ValueError(f"summary note has no {next_heading} heading")
        end = start + end_match.start()
    value = body[start:end].strip()
    if not value:
        raise ValueError(f"{heading} section is empty")
    return value


def validate_summary_text(text: str, *, verify_source: bool = True) -> list[str]:
    errors: list[str] = []
    try:
        metadata, body = split_frontmatter(text)
    except ValueError as exc:
        return [str(exc)]
    if _frontmatter_keys(text) != SUMMARY_FRONTMATTER_ORDER:
        errors.append("summary frontmatter fields are missing or out of order")
    if metadata.get("type") != "webClip":
        errors.append("type must be 'webClip'")
    if str(metadata.get("schemaVersion")) != SUMMARY_SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SUMMARY_SCHEMA_VERSION}")
    if metadata.get("cliptool") != "Codex":
        errors.append("cliptool must be 'Codex'")
    if metadata.get("nouns") != []:
        errors.append("nouns must default to []")
    if metadata.get("reviewStatus") not in REVIEW_STATUSES:
        errors.append("reviewStatus must be one of: " + ", ".join(REVIEW_STATUSES))
    for key in (
        "title",
        "description",
        "url",
        "source",
        "sourceSha256",
        "generator",
        "promptId",
        "promptVersion",
        "promptSha256",
        "promptEnvelopeVersion",
        "date",
        "updated",
        "noteId",
    ):
        if not metadata.get(key):
            errors.append(f"{key} must be non-empty")
    for key in ("sourceSha256", "promptSha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get(key) or "")):
            errors.append(f"{key} must be a lowercase SHA-256 digest")
    for key in ("promptId", "noteId"):
        try:
            normalized = str(uuid.UUID(str(metadata.get(key))))
            if normalized != str(metadata.get(key)):
                errors.append(f"{key} must use canonical lowercase UUID form")
        except (ValueError, AttributeError):
            errors.append(f"{key} must be a UUID")
    headings = [
        "## 1. Summary",
        "## 2. Structuring (from abstract to concrete)",
        "## 3. Key points",
        "## 4. Technical terms",
        "## 5. Conclusion",
    ]
    positions = [body.find(heading) for heading in headings]
    if any(position < 0 for position in positions):
        errors.append("summary headings are incomplete")
    elif positions != sorted(positions):
        errors.append("summary headings are out of order")
    else:
        for index, heading in enumerate(headings):
            next_heading = headings[index + 1] if index + 1 < len(headings) else None
            try:
                _section(body, heading, next_heading)
            except ValueError as exc:
                errors.append(str(exc))
    terms_match = re.search(
        r"(?ms)^## 4\. Technical terms\s*$\n(.*?)^## 5\. Conclusion\s*$",
        body,
    )
    if terms_match:
        terms = [
            line[2:].strip() for line in terms_match.group(1).splitlines() if line.startswith("- ")
        ]
        for term in terms:
            if not re.match(r"^\*\*.+?\*\*:\s+\S", term):
                errors.append("technical terms must use '**term**: explanation' format")
                break
    if verify_source:
        try:
            source_path = file_uri_to_path(str(metadata.get("source") or ""))
            payload = source_path.read_bytes()
            if sha256_bytes(payload) != metadata.get("sourceSha256"):
                errors.append("sourceSha256 does not match the referenced source file")
        except (OSError, ValueError) as exc:
            errors.append(f"cannot validate source reference: {exc}")
    return errors


def validate_summary(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"cannot read summary note: {exc}"]
    return validate_summary_text(text)
