"""Source attribution checks for structured post-meeting minutes."""

from __future__ import annotations

from doc_summarizer.models import MeetingMinutesDocument


def validate_meeting_minutes_document(
    document: MeetingMinutesDocument,
    *,
    source_ids: set[str],
    has_context: bool,
) -> list[str]:
    errors: list[str] = []
    facts = [item for topic in document.facts for item in topic.items]
    points = [
        *document.summary, *facts, *document.open_questions, *document.raid, *document.next_checks,
    ]
    used: set[str] = set()
    for point in points:
        ids = set(point.source_ids)
        if ids - source_ids or len(ids) != len(point.source_ids):
            errors.append("meeting minutes contain unknown or duplicate source ids")
        if point.basis == "context":
            if not has_context or ids:
                errors.append("context-only points require context and no source ids")
        elif not ids and (point.basis != "interpretation" or not has_context):
            errors.append("meeting minutes require source ids for source-grounded points")
        used.update(ids)
    if source_ids - used:
        errors.append("meeting minutes omit supplied source ids")
    if any(point.basis in ("context", "interpretation") for point in facts):
        errors.append("meeting facts must not include context-only claims or interpretation")
    return errors
