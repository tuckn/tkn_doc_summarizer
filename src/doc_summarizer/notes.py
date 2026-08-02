"""Render and inspect generated Markdown summary notes."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from doc_summarizer.models import DocumentSource, SummaryDocument
from doc_summarizer.source import split_frontmatter
from doc_summarizer.summary_resources import SummaryProfile, render_summary_template

SUMMARY_SCHEMA_VERSION = "5.0"
DESCRIPTION_MAX_CHARS = 240
REVIEW_STATUSES = (
    "unreviewed",
    "pending",
    "reviewing",
    "accepted",
    "needs-revision",
    "rejected",
)


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def yaml_optional(value: str | None) -> str:
    return yaml_quote(value) if value else "null"


def compact_description(value: str, max_chars: int = DESCRIPTION_MAX_CHARS) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    boundary = max(normalized.rfind(mark, 0, max_chars) for mark in "。！？.!?")
    if boundary >= max_chars // 2:
        return normalized[: boundary + 1]
    return normalized[: max_chars - 1].rstrip() + "…"


def frontmatter_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def path_to_file_uri(path: Path) -> str:
    return path.absolute().as_uri()


def file_uri_to_path(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme != "file":
        raise ValueError("source must be a file URI")
    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return Path(path)


def render_summary(
    *,
    source: DocumentSource,
    document: SummaryDocument,
    now: datetime,
    generator: str,
    profile: SummaryProfile,
    prompt_envelope_version: str,
    note_id: str | None = None,
    created_at: datetime | None = None,
) -> str:
    created = created_at or now
    source_uri = path_to_file_uri(source.path)
    canonical_reference = source.url or source_uri
    prompt = profile.prompt
    template = profile.template
    frontmatter_lines = [
        "---",
        "type: summary",
        f"schemaVersion: {yaml_quote(SUMMARY_SCHEMA_VERSION)}",
        f"title: {yaml_quote(source.title)}",
        f"description: {yaml_quote(compact_description(document.description))}",
        f"cover: {yaml_optional(source.cover)}",
        f"url: {yaml_quote(canonical_reference)}",
        "cliptool: Codex",
        f"source: {yaml_quote(source_uri)}",
        f"sourceSha256: {source.source_sha256}",
        f"generator: {yaml_quote(generator)}",
        f"promptId: {prompt.prompt_id}",
        f"promptVersion: {yaml_quote(prompt.version)}",
        f"promptSha256: {prompt.sha256}",
        f"summaryProfile: {yaml_quote(profile.name)}",
        f"summaryProfileSha256: {profile.sha256}",
        f"outputSchemaSha256: {profile.schema.sha256}",
        f"templateId: {template.template_id}",
        f"templateVersion: {yaml_quote(template.version)}",
        f"templateSha256: {template.sha256}",
        f"promptEnvelopeVersion: {yaml_quote(prompt_envelope_version)}",
        "reviewStatus: unreviewed",
        f"date: {created.isoformat(timespec='seconds')}",
        f"updated: {now.isoformat(timespec='seconds')}",
        f"noteId: {note_id or uuid.uuid4()}",
        "---",
    ]
    structuring_lines: list[str] = []
    for section in document.structuring:
        structuring_lines.extend([f"### {section.heading.strip()}", ""])
        structuring_lines.extend(f"- {detail.strip()}" for detail in section.details)
        if section.details:
            structuring_lines.append("")
        for subsection in section.subsections:
            structuring_lines.extend(
                [
                    f"#### {subsection.heading.strip()}",
                    "",
                    *(f"- {detail.strip()}" for detail in subsection.details),
                    "",
                ]
            )
    return render_summary_template(
        template,
        {
            "frontmatter": "\n".join(frontmatter_lines),
            "title": source.title,
            "cover": f"![]({source.cover})\n\n" if source.cover else "",
            "summary": document.summary.strip(),
            "structuring": "\n".join(structuring_lines),
            "key_points": "\n".join(f"- {point.strip()}" for point in document.key_points),
            "technical_terms": "\n".join(f"- {term.strip()}" for term in document.technical_terms),
            "conclusion": document.conclusion.strip(),
        },
    )


def summary_metadata(path: Path) -> dict[str, Any]:
    metadata, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    return metadata
