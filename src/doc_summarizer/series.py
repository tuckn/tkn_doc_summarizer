"""Resolve ordered CLI sources into one logical series document."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from doc_summarizer.io import sha256_bytes
from doc_summarizer.models import DocumentSourceSet, SeriesSource
from doc_summarizer.source import resolve_source


def source_set_identity_payload(source_set: DocumentSourceSet) -> dict[str, object]:
    return {
        "sourceSetId": source_set.source_set_id,
        "title": source_set.title,
        "mode": source_set.mode,
        "cover": source_set.cover,
        "published": source_set.published,
        "sources": [
            {
                "id": entry.id,
                "source": entry.document.path.absolute().as_uri(),
                "sourceSha256": entry.document.source_sha256,
            }
            for entry in source_set.sources
        ],
    }


def source_set_sha256(source_set: DocumentSourceSet) -> str:
    payload = json.dumps(
        source_set_identity_payload(source_set),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def metadata_source_set_sha256(metadata: dict[str, object]) -> str:
    identity = {
        "sourceSetId": str(metadata.get("sourceSetId") or ""),
        "title": str(metadata.get("title") or ""),
        "mode": str(metadata.get("synthesisMode") or ""),
        "cover": metadata.get("cover"),
        "published": metadata.get("sourceSetPublished"),
        "sources": metadata.get("sources"),
    }
    payload = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def _series_id(sources: list[SeriesSource]) -> str:
    ordered_references = json.dumps(
        [entry.document.path.absolute().as_uri() for entry in sources],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tkn-doc-summarizer:series:{ordered_references}"))


def resolve_series_sources(
    source_values: list[str],
    *,
    title: str | None,
    source_roots: list[Path],
    max_input_bytes: int,
    max_total_input_bytes: int,
) -> DocumentSourceSet:
    if len(source_values) < 2:
        raise ValueError("series synthesis requires at least two sources")
    resolved: list[SeriesSource] = []
    seen_paths: dict[str, str] = {}
    total_bytes = 0
    for index, source_value in enumerate(source_values, start=1):
        document = resolve_source(
            source_value,
            source_roots=source_roots,
            max_input_bytes=max_input_bytes,
        )
        source_id = f"S{index}"
        key = str(document.path.resolve()).casefold()
        if key in seen_paths:
            raise ValueError(
                "series resolves the same local source more than once: "
                f"{seen_paths[key]}, {source_id}: {document.path}"
            )
        seen_paths[key] = source_id
        total_bytes += document.source_size_bytes
        if total_bytes > max_total_input_bytes:
            raise ValueError(
                f"series exceeds max_total_input_bytes ({total_bytes} > {max_total_input_bytes})"
            )
        resolved.append(SeriesSource(id=source_id, document=document))
    effective_title = title.strip() if title is not None else resolved[0].document.title
    if not effective_title:
        raise ValueError("--title must not be empty")
    source_set = DocumentSourceSet(
        source_set_id=_series_id(resolved),
        title=effective_title,
        mode="series",
        cover=resolved[0].document.cover,
        published=resolved[0].document.published,
        sources=resolved,
        source_set_sha256="0" * 64,
    )
    return source_set.model_copy(update={"source_set_sha256": source_set_sha256(source_set)})
