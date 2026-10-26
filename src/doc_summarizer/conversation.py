"""Ground conversation evidence in file-local transcript segments."""

from __future__ import annotations

import re
from datetime import date

from doc_summarizer.models import (
    ConversationDocument,
    ConversationEvidence,
    DocumentSource,
    SeriesSummaryRequest,
    SummaryGenerationRequest,
)

TIMESTAMP = r"[0-9]{2,}:[0-5][0-9]:[0-5][0-9]"
SEGMENT = re.compile(
    rf"(?m)^\[(?P<start>{TIMESTAMP})\s*-\s*(?P<end>{TIMESTAMP})\]"
    r"(?:[ \t]*\[(?P<speaker>[^\]\r\n]+)\])?"
)
CITATION = re.compile(
    rf"\[(?P<id>S[1-9][0-9]*) (?P<time>{TIMESTAMP}–{TIMESTAMP}|時刻不明)"
    r" / (?P<speaker>[^\]\r\n]+)\]\((?P<link>[^)\r\n]+)\)"
)


def validate_conversation_date(value: str | None) -> str | None:
    if value is not None:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            raise ValueError("--conversation-date must use YYYY-MM-DD")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("--conversation-date must be a valid calendar date") from None
    return value


def request_sources(request: SummaryGenerationRequest) -> dict[str, DocumentSource]:
    if isinstance(request, SeriesSummaryRequest):
        return {entry.id: entry.document for entry in request.source_set.sources}
    return {"S1": request.source}


def _seconds(value: str) -> int:
    hours, minutes, seconds = map(int, value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def evidence_errors(evidence: ConversationEvidence, content: str) -> list[str]:
    """Check boundaries and labels, without claiming the paraphrase is true."""
    segments = list(SEGMENT.finditer(content))
    if (evidence.start is None) != (evidence.end is None):
        return ["evidence start and end must both be present or both null"]
    if evidence.start is None or evidence.end is None:
        if segments:
            return ["timestamped source requires file-local evidence timestamps"]
        if evidence.speaker_label is not None and f"[{evidence.speaker_label}]" not in content:
            return ["evidence speaker label is absent from source"]
        return []
    start, end = _seconds(evidence.start), _seconds(evidence.end)
    if end < start:
        return ["evidence end precedes start"]
    matching = [
        segment
        for segment in segments
        if start <= _seconds(segment["start"]) and _seconds(segment["end"]) <= end
    ]
    if (
        not matching
        or not any(s["start"] == evidence.start for s in matching)
        or not any(s["end"] == evidence.end for s in matching)
    ):
        return ["evidence timestamps do not match source segment boundaries"]
    labels = {segment["speaker"] for segment in matching}
    if evidence.speaker_label not in labels:
        return ["evidence speaker label is absent from the cited time range"]
    return []


def validate_conversation_document(
    document: ConversationDocument, *, sources: dict[str, DocumentSource]
) -> list[str]:
    errors: list[str] = []
    used: set[str] = set()
    items = [item for topic in document.topics for item in topic.items]
    items.extend(document.plans)
    items.extend(document.unconfirmed)
    for item in items:
        for evidence in item.evidence:
            used.add(evidence.source_id)
            if evidence.source_id not in sources:
                errors.append("conversation evidence references an unknown source id")
            else:
                errors.extend(evidence_errors(evidence, sources[evidence.source_id].content))
    if set(sources) - used:
        errors.append("conversation record omits supplied source ids")
    if any(item.kind not in {"wish", "plan", "commitment"} for item in document.plans):
        errors.append("plans must distinguish wishes, proposed plans, and commitments")
    return errors
