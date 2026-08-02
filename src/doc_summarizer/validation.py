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

LEGACY_SUMMARY_FRONTMATTER_ORDER = [
    "type",
    "schemaVersion",
    "title",
    "description",
    "cover",
    "url",
    "cliptool",
    "source",
    "sourceSha256",
    "generator",
    "promptId",
    "promptVersion",
    "promptSha256",
    "promptEnvelopeVersion",
    "reviewStatus",
    "date",
    "updated",
    "noteId",
]
SUMMARY_FRONTMATTER_ORDER = [
    *LEGACY_SUMMARY_FRONTMATTER_ORDER[:13],
    "summaryProfile",
    "summaryProfileSha256",
    "outputSchemaSha256",
    "templateId",
    "templateVersion",
    "templateSha256",
    *LEGACY_SUMMARY_FRONTMATTER_ORDER[13:],
]
PROFILED_SUMMARY_SCHEMA_VERSIONS = ("4.0", SUMMARY_SCHEMA_VERSION)
SUPPORTED_SUMMARY_SCHEMA_VERSIONS = (
    "2.0",
    "3.0",
    *PROFILED_SUMMARY_SCHEMA_VERSIONS,
)
ENGLISH_HEADINGS = (
    "## 1. Summary",
    "## 2. Structuring (from abstract to concrete)",
    "## 3. Key points",
    "## 4. Technical terms",
    "## 5. Conclusion",
)
JAPANESE_HEADINGS = (
    "## 1. 要約",
    "## 2. 構造化（抽象から具体へ）",
    "## 3. 重要ポイント",
    "## 4. 専門用語",
    "## 5. 結論",
)


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


def _summary_headings(metadata: dict[str, object], schema_version: str) -> tuple[str, ...]:
    if schema_version == SUMMARY_SCHEMA_VERSION and metadata.get("summaryProfile") == "default-ja":
        return JAPANESE_HEADINGS
    return ENGLISH_HEADINGS


def validate_summary_text(text: str, *, verify_source: bool = True) -> list[str]:
    errors: list[str] = []
    try:
        metadata, body = split_frontmatter(text)
    except ValueError as exc:
        return [str(exc)]
    schema_version = str(metadata.get("schemaVersion"))
    expected_order = (
        SUMMARY_FRONTMATTER_ORDER
        if schema_version in PROFILED_SUMMARY_SCHEMA_VERSIONS
        else LEGACY_SUMMARY_FRONTMATTER_ORDER
    )
    if _frontmatter_keys(text) != expected_order:
        errors.append("summary frontmatter fields are missing or out of order")
    if metadata.get("type") != "summary":
        errors.append("type must be 'summary'")
    if schema_version not in SUPPORTED_SUMMARY_SCHEMA_VERSIONS:
        allowed = ", ".join(SUPPORTED_SUMMARY_SCHEMA_VERSIONS)
        errors.append(f"schemaVersion must be one of: {allowed}")
    if metadata.get("cliptool") != "Codex":
        errors.append("cliptool must be 'Codex'")
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
    if schema_version in PROFILED_SUMMARY_SCHEMA_VERSIONS:
        for key in (
            "summaryProfile",
            "summaryProfileSha256",
            "outputSchemaSha256",
            "templateId",
            "templateVersion",
            "templateSha256",
        ):
            if not metadata.get(key):
                errors.append(f"{key} must be non-empty")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(metadata.get("summaryProfile") or "")):
            errors.append("summaryProfile must use a lowercase kebab-case name")
    digest_keys = ["sourceSha256", "promptSha256"]
    if schema_version in PROFILED_SUMMARY_SCHEMA_VERSIONS:
        digest_keys.extend(["summaryProfileSha256", "outputSchemaSha256", "templateSha256"])
    for key in digest_keys:
        if not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get(key) or "")):
            errors.append(f"{key} must be a lowercase SHA-256 digest")
    uuid_keys = ["promptId", "noteId"]
    if schema_version in PROFILED_SUMMARY_SCHEMA_VERSIONS:
        uuid_keys.append("templateId")
    for key in uuid_keys:
        try:
            normalized = str(uuid.UUID(str(metadata.get(key))))
            if normalized != str(metadata.get(key)):
                errors.append(f"{key} must use canonical lowercase UUID form")
        except (ValueError, AttributeError):
            errors.append(f"{key} must be a UUID")
    headings = _summary_headings(metadata, schema_version)
    if schema_version in ("3.0", *PROFILED_SUMMARY_SCHEMA_VERSIONS) and metadata.get("cover"):
        title_heading = f"# {metadata.get('title')}"
        cover_embed = f"![]({metadata.get('cover')})"
        title_position = body.find(title_heading)
        embed_position = body.find(cover_embed)
        summary_position = body.find(headings[0])
        if embed_position < 0:
            errors.append("summary body must contain the cover image")
        elif title_position < 0 or not (title_position < embed_position < summary_position):
            errors.append(
                "summary cover image must appear after the title and before the first section"
            )
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
        rf"(?ms)^{re.escape(headings[3])}\s*$\n(.*?)^{re.escape(headings[4])}\s*$",
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
