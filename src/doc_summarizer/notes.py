"""Render and inspect generated Markdown summary notes."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from doc_summarizer.comparison_resources import ComparisonProfile, render_comparison_template
from doc_summarizer.config import SourcePathFormat
from doc_summarizer.models import (
    ComparisonDocument,
    ConversationDocument,
    ConversationItem,
    DocumentSource,
    DocumentSourceSet,
    GeneratedSummaryDocument,
    MeetingMinutesDocument,
    MeetingPoint,
)
from doc_summarizer.source import split_frontmatter
from doc_summarizer.summary_resources import SummaryProfile, render_summary_template
from doc_summarizer.yaml_format import quote_scalar

SUMMARY_SCHEMA_VERSION = "8.0"
SERIES_SUMMARY_SCHEMA_VERSION = "9.0"
COMPARISON_SUMMARY_SCHEMA_VERSION = "7.0"
CONVERSATION_SCHEMA_VERSION = "10.0"
CONVERSATION_SERIES_SCHEMA_VERSION = "11.0"
MEETING_MINUTES_SCHEMA_VERSION = "12.0"
MEETING_MINUTES_SERIES_SCHEMA_VERSION = "13.0"
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
    return quote_scalar(value)


def yaml_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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


def frontmatter_timestamp(value: str | datetime) -> str:
    """Preserve existing timestamps; newly generated times use local time and seconds."""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def path_to_file_uri(path: Path) -> str:
    return path.absolute().as_uri()


def path_to_native_reference(path: Path) -> str:
    # Match file URI and source-set identity paths, including Windows junction aliases.
    return str(path.absolute())


def path_to_source_reference(path: Path, source_path_format: SourcePathFormat) -> str:
    if source_path_format == "file-uri":
        return path_to_file_uri(path)
    return path_to_native_reference(path)


def yaml_source_reference(path: Path, source_path_format: SourcePathFormat) -> str:
    value = path_to_source_reference(path, source_path_format)
    return yaml_quote(value) if source_path_format == "file-uri" else yaml_single_quote(value)


def source_reference_format(value: str) -> SourcePathFormat:
    return "file-uri" if urlparse(value).scheme == "file" else "native"


def source_reference_to_path(value: str) -> Path:
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\"):
        return Path(value)
    parsed = urlparse(value)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
        return Path(path)
    if parsed.scheme:
        raise ValueError("source must be an absolute OS path or file URI")
    native_path = Path(value)
    if not native_path.is_absolute():
        raise ValueError("source must be an absolute OS path or file URI")
    return native_path


def file_uri_to_path(value: str) -> Path:
    """Read legacy file URIs and current native source paths."""
    return source_reference_to_path(value)


def render_summary(
    *,
    source: DocumentSource,
    document: GeneratedSummaryDocument,
    now: datetime,
    generator: str,
    profile: SummaryProfile,
    prompt_envelope_version: str,
    source_path_format: SourcePathFormat,
    note_id: str | None = None,
    created_at: str | datetime | None = None,
    conversation_date: str | None = None,
    context_sha256: str | None = None,
) -> str:
    created = created_at or now
    source_uri = path_to_file_uri(source.path)
    canonical_reference = source.url or source_uri
    prompt = profile.prompt
    template = profile.template
    schema_version = (
        MEETING_MINUTES_SCHEMA_VERSION
        if isinstance(document, MeetingMinutesDocument)
        else CONVERSATION_SCHEMA_VERSION
        if isinstance(document, ConversationDocument)
        else SUMMARY_SCHEMA_VERSION
    )
    description = (
        " ".join(point.text for point in document.summary)
        if isinstance(document, MeetingMinutesDocument)
        else document.summary if isinstance(document, ConversationDocument) else document.conclusion
    )
    title = document.title if isinstance(document, MeetingMinutesDocument) else source.title
    frontmatter_lines = [
        "---",
        "type: summary",
        f"schemaVersion: {yaml_quote(schema_version)}",
        f"title: {yaml_quote(title)}",
        f"description: {yaml_quote(compact_description(description))}",
        f"cover: {yaml_optional(source.cover)}",
        f"url: {yaml_quote(canonical_reference)}",
        "cliptool: Codex",
        *(
            [f"conversationDate: {yaml_optional(conversation_date)}"]
            if isinstance(document, ConversationDocument | MeetingMinutesDocument)
            else []
        ),
        f"source: {yaml_source_reference(source.path, source_path_format)}",
        f"sourceSha256: {source.source_sha256}",
        f"generator: {yaml_quote(generator)}",
        f"promptId: {prompt.prompt_id}",
        f"promptVersion: {yaml_quote(prompt.version)}",
        f"promptSha256: {prompt.sha256}",
        f"summaryProfile: {yaml_quote(profile.name)}",
        f"summaryProfileSha256: {profile.sha256}",
        f"outputSchemaId: {profile.schema.resource_id}",
        f"outputSchemaVersion: {yaml_quote(profile.schema.version)}",
        f"outputSchemaSha256: {profile.schema.sha256}",
        f"templateId: {template.template_id}",
        f"templateVersion: {yaml_quote(template.version)}",
        f"templateSha256: {template.sha256}",
        *([f"contextSha256: {context_sha256}"] if context_sha256 is not None else []),
        f"promptEnvelopeVersion: {yaml_quote(prompt_envelope_version)}",
        "reviewStatus: unreviewed",
        f"created: {yaml_quote(frontmatter_timestamp(created))}",
        f"updated: {yaml_quote(frontmatter_timestamp(now))}",
        f"noteId: {note_id or uuid.uuid4()}",
        "---",
    ]
    return _render_summary_body(
        frontmatter_lines=frontmatter_lines,
        title=title,
        cover=source.cover,
        document=document,
        profile=profile,
        sources={"S1": source},
        conversation_date=conversation_date,
    )


def _render_summary_body(
    *,
    frontmatter_lines: list[str],
    title: str,
    cover: str | None,
    document: GeneratedSummaryDocument,
    profile: SummaryProfile,
    sources: dict[str, DocumentSource],
    conversation_date: str | None,
) -> str:
    if isinstance(document, MeetingMinutesDocument):
        return _render_meeting_minutes_body(
            frontmatter_lines=frontmatter_lines,
            title=title,
            cover=cover,
            document=document,
            profile=profile,
            sources=sources,
            conversation_date=conversation_date,
        )
    if isinstance(document, ConversationDocument):
        return _render_conversation_body(
            frontmatter_lines=frontmatter_lines,
            title=title,
            cover=cover,
            document=document,
            profile=profile,
            sources=sources,
            conversation_date=conversation_date,
        )
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
        profile.template,
        {
            "frontmatter": "\n".join(frontmatter_lines),
            "title": title,
            "cover": f"![]({cover})\n\n" if cover else "",
            "summary": document.summary.strip(),
            "structuring": "\n".join(structuring_lines).rstrip(),
            "key_points": "\n".join(f"- {point.strip()}" for point in document.key_points),
            "technical_terms": "\n".join(f"- {term.strip()}" for term in document.technical_terms),
            "conclusion": document.conclusion.strip(),
        },
    )


def render_series_summary(
    *,
    source_set: DocumentSourceSet,
    document: GeneratedSummaryDocument,
    now: datetime,
    generator: str,
    profile: SummaryProfile,
    prompt_envelope_version: str,
    source_path_format: SourcePathFormat,
    note_id: str | None = None,
    created_at: str | datetime | None = None,
    context_sha256: str | None = None,
) -> str:
    created = created_at or now
    first_source = source_set.sources[0].document
    canonical_reference = first_source.url or path_to_file_uri(first_source.path)
    prompt = profile.prompt
    template = profile.template
    schema_version = (
        MEETING_MINUTES_SERIES_SCHEMA_VERSION
        if isinstance(document, MeetingMinutesDocument)
        else CONVERSATION_SERIES_SCHEMA_VERSION
        if isinstance(document, ConversationDocument)
        else SERIES_SUMMARY_SCHEMA_VERSION
    )
    description = (
        " ".join(point.text for point in document.summary)
        if isinstance(document, MeetingMinutesDocument)
        else document.summary if isinstance(document, ConversationDocument) else document.conclusion
    )
    frontmatter_lines = [
        "---",
        "type: summary",
        f"schemaVersion: {yaml_quote(schema_version)}",
        f"title: {yaml_quote(source_set.title)}",
        f"description: {yaml_quote(compact_description(description))}",
        f"cover: {yaml_optional(source_set.cover)}",
        f"url: {yaml_quote(canonical_reference)}",
        "cliptool: Codex",
        *(
            [f"conversationDate: {yaml_optional(source_set.conversation_date)}"]
            if isinstance(document, ConversationDocument | MeetingMinutesDocument)
            else []
        ),
        "synthesisMode: series",
        f"sourceSetId: {source_set.source_set_id}",
        f"sourceSetPublished: {yaml_optional(source_set.published)}",
        f"sourceSetSha256: {source_set.source_set_sha256}",
        "sources:",
    ]
    for entry in source_set.sources:
        source = entry.document
        frontmatter_lines.extend(
            [
                f"  - id: {yaml_quote(entry.id)}",
                f"    source: {yaml_source_reference(source.path, source_path_format)}",
                f"    sourceSha256: {source.source_sha256}",
            ]
        )
    frontmatter_lines.extend(
        [
            f"generator: {yaml_quote(generator)}",
            f"promptId: {prompt.prompt_id}",
            f"promptVersion: {yaml_quote(prompt.version)}",
            f"promptSha256: {prompt.sha256}",
            f"summaryProfile: {yaml_quote(profile.name)}",
            f"summaryProfileSha256: {profile.sha256}",
            f"outputSchemaId: {profile.schema.resource_id}",
            f"outputSchemaVersion: {yaml_quote(profile.schema.version)}",
            f"outputSchemaSha256: {profile.schema.sha256}",
            f"templateId: {template.template_id}",
            f"templateVersion: {yaml_quote(template.version)}",
            f"templateSha256: {template.sha256}",
            *([f"contextSha256: {context_sha256}"] if context_sha256 is not None else []),
            f"promptEnvelopeVersion: {yaml_quote(prompt_envelope_version)}",
            "reviewStatus: unreviewed",
            f"created: {yaml_quote(frontmatter_timestamp(created))}",
            f"updated: {yaml_quote(frontmatter_timestamp(now))}",
            f"noteId: {note_id or uuid.uuid4()}",
            "---",
        ]
    )
    return _render_summary_body(
        frontmatter_lines=frontmatter_lines,
        title=source_set.title,
        cover=source_set.cover,
        document=document,
        profile=profile,
        sources={entry.id: entry.document for entry in source_set.sources},
        conversation_date=source_set.conversation_date,
    )


def _render_meeting_minutes_body(
    *,
    frontmatter_lines: list[str],
    title: str,
    cover: str | None,
    document: MeetingMinutesDocument,
    profile: SummaryProfile,
    sources: dict[str, DocumentSource],
    conversation_date: str | None,
) -> str:
    bases = {
        "statement": "発言",
        "document": "資料記載",
        "context": "ユーザー補足",
        "interpretation": "解釈",
    }
    certainties = {
        "confirmed": "確定",
        "provisional": "暫定",
        "needs-confirmation": "要確認",
    }

    def line(value: str) -> str:
        return " ".join(value.split()).replace("|", "&#124;")

    def point_text(point: MeetingPoint) -> str:
        citations = " ".join(
            f"[{source_id}]({path_to_file_uri(sources[source_id].path)})"
            for source_id in point.source_ids
        )
        return (
            f"【{bases[point.basis]}・{certainties[point.certainty]}】"
            f"{line(point.text)} {citations}"
        ).rstrip()

    counters = dict.fromkeys(("Risk", "Action", "Issue", "Decision"), 0)
    rows = [
        "| ID | 区分 | 内容・根拠 | オーナー | 期限 | 状態 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in document.raid:
        counters[item.category] += 1
        item_id = f"{item.category[0]}{counters[item.category]}"
        rows.append(
            f"| {item_id} | {item.category} | {point_text(item)} | {line(item.owner)} | "
            f"{line(item.deadline)} | {line(item.status)} |"
        )
    meeting_info = (
        f"**会議情報**：会話日: {conversation_date or '未確認'}。"
        "話者ラベルは参考情報であり、実名・人数を確定するものではありません。\n\n"
        "**根拠の扱い**：発言・資料記載・ユーザー補足・解釈を各項目で区別します。"
        "「確定」は独立した外部事実の検証済みを意味しません。\n\n"
        "**出典**："
        + " / ".join(
            f"[{source_id} · {_markdown_label(source.title)}]({path_to_file_uri(source.path)})"
            for source_id, source in sources.items()
        )
        + "\n\n**読み取り上の制約**：\n\n"
        + "\n".join(f"- {line(value)}" for value in document.limitations)
    )
    return render_summary_template(
        profile.template,
        {
            "frontmatter": "\n".join(frontmatter_lines),
            "title": title,
            "cover": f"![]({cover})\n\n" if cover else "",
            "summary": "\n".join(f"- {point_text(point)}" for point in document.summary)
            + "\n\n" + meeting_info,
            "facts": "\n\n".join(
                f"### {line(topic.heading)}\n\n"
                + "\n".join(f"- {point_text(point)}" for point in topic.items)
                for topic in document.facts
            ) or "会話で確認できた事実は抽出されていません。",
            "open_questions": "\n".join(
                f"- {point_text(point)}" for point in document.open_questions
            ) or "認識差・未決事項は抽出されていません。",
            "raid": "\n".join(rows)
            + ("" if document.raid else "\n\nRAID に該当する項目は抽出されていません。"),
            "next_checks": "\n".join(
                f"{index}. {point_text(point)}"
                for index, point in enumerate(document.next_checks, start=1)
            ) or "次回確認事項は抽出されていません。",
        },
    )


def _render_conversation_body(
    *,
    frontmatter_lines: list[str],
    title: str,
    cover: str | None,
    document: ConversationDocument,
    profile: SummaryProfile,
    sources: dict[str, DocumentSource],
    conversation_date: str | None,
) -> str:
    kinds = {
        "statement": "発言・体験談",
        "hearsay": "伝聞",
        "joke": "冗談",
        "speculation": "推測",
        "wish": "願望",
        "plan": "予定案",
        "commitment": "約束・決定",
    }
    identities = {"unknown": "未確認", "inferred": "推定", "confirmed": "明示確認"}

    def line(value: str) -> str:
        return " ".join(value.split())

    def item_text(item: ConversationItem) -> str:
        citations = " ".join(
            f"[{e.source_id} {e.start + '–' + str(e.end) if e.start else '時刻不明'}"
            f" / {e.speaker_label or '話者ラベルなし'}]"
            f"({path_to_file_uri(sources[e.source_id].path)})"
            for e in item.evidence
        )
        return (
            f"- {line(item.text)}（種別: {kinds[item.kind]} / 対象: {line(item.subject)} / "
            f"話者: {line(item.speaker_name or '不明')}・{identities[item.identity_status]} / "
            f"同定根拠: {line(item.identity_basis)} / 留保: {line(item.uncertainty)}） {citations}"
        )

    meeting = [
        f"- 会話日: {conversation_date or '未確認'}（文字起こし・要約の生成日とは別）",
        "- 参加者と実名対応: 下記の各項目で確認状態を表示。話者ラベルから人数は確定しない。",
        "- 出典時刻: 各ファイルの先頭からの経過時間。録音間でリセットされる。",
        "- 同じ話者ラベルでも別ファイルでは別の識別子。同一ファイル内の分離誤りもあり得る。",
        *[
            f"- [{source_id} · {_markdown_label(source.title)}]({path_to_file_uri(source.path)})"
            + (f" — 資料の記録日時: {source.published}" if source.published else "")
            for source_id, source in sources.items()
        ],
    ]
    return render_summary_template(
        profile.template,
        {
            "frontmatter": "\n".join(frontmatter_lines),
            "title": title,
            "cover": f"![]({cover})\n\n" if cover else "",
            "meeting": "\n".join(meeting),
            "summary": document.summary.strip(),
            "topics": "\n\n".join(
                f"### {line(topic.heading)}\n\n" + "\n".join(map(item_text, topic.items))
                for topic in document.topics
            ),
            "plans": "\n".join(map(item_text, document.plans))
            or "記録対象の約束・予定・願望は抽出されていません。",
            "unconfirmed": (
                "\n".join(map(item_text, document.unconfirmed))
                or "個別の未確認項目は抽出されていません。"
            )
            + "\n\n### 読み取り上の制約\n\n"
            + "- 文字起こしに基づく記録。音声の再確認・発言内容の事実検証は行っていません。\n"
            + "\n".join(f"- {line(value)}" for value in document.limitations),
        },
    )


def _source_citation(source_ids: list[str], links: dict[str, str] | None = None) -> str:
    if links is not None:
        return " ".join(f"[{source_id}]({links[source_id]})" for source_id in source_ids)
    return "[" + ", ".join(source_ids) + "]"


def _source_link(path: Path, output_path: Path | None) -> str:
    if output_path is not None:
        try:
            relative = os.path.relpath(path.absolute(), output_path.absolute().parent)
        except ValueError:  # Different Windows drives cannot share a relative path.
            pass
        else:
            return quote(Path(relative).as_posix(), safe="/:")
    return path_to_file_uri(path)


def _markdown_label(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", r"\[").replace("]", r"\]")


def render_comparison_summary(
    *,
    source_set: DocumentSourceSet,
    document: ComparisonDocument,
    now: datetime,
    generator: str,
    profile: ComparisonProfile,
    prompt_envelope_version: str,
    source_path_format: SourcePathFormat,
    output_path: Path | None = None,
    note_id: str | None = None,
    created_at: str | datetime | None = None,
    context_sha256: str | None = None,
) -> str:
    created = created_at or now
    first_source = source_set.sources[0].document
    canonical_reference = first_source.url or path_to_file_uri(first_source.path)
    prompt = profile.prompt
    template = profile.template
    frontmatter_lines = [
        "---",
        "type: summary",
        f"schemaVersion: {yaml_quote(COMPARISON_SUMMARY_SCHEMA_VERSION)}",
        f"title: {yaml_quote(source_set.title)}",
        f"description: {yaml_quote(compact_description(document.description))}",
        f"cover: {yaml_optional(source_set.cover)}",
        f"url: {yaml_quote(canonical_reference)}",
        "cliptool: Codex",
        "synthesisMode: compare",
        f"sourceSetId: {source_set.source_set_id}",
        f"sourceSetPublished: {yaml_optional(source_set.published)}",
        f"sourceSetSha256: {source_set.source_set_sha256}",
        "sources:",
    ]
    for entry in source_set.sources:
        source = entry.document
        frontmatter_lines.extend(
            [
                f"  - id: {yaml_quote(entry.id)}",
                f"    source: {yaml_source_reference(source.path, source_path_format)}",
                f"    sourceSha256: {source.source_sha256}",
            ]
        )
    frontmatter_lines.extend(
        [
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
            *([f"contextSha256: {context_sha256}"] if context_sha256 is not None else []),
            f"promptEnvelopeVersion: {yaml_quote(prompt_envelope_version)}",
            "reviewStatus: unreviewed",
            f"created: {yaml_quote(frontmatter_timestamp(created))}",
            f"updated: {yaml_quote(frontmatter_timestamp(now))}",
            f"noteId: {note_id or uuid.uuid4()}",
            "---",
        ]
    )
    links = (
        {entry.id: _source_link(entry.document.path, output_path) for entry in source_set.sources}
        if profile.name == "claims-ja"
        else None
    )
    common_concepts = "\n".join(
        f"- {item.text.strip()} {_source_citation(item.source_ids, links)}"
        for item in document.common_concepts
    )
    perspectives = "\n\n".join(
        f"### {item.heading.strip()}\n\n"
        f"{item.explanation.strip()} {_source_citation(item.source_ids, links)}"
        for item in document.perspectives
    )
    disagreement_groups = [
        f"### {item.topic.strip()}\n\n"
        + "\n".join(
            f"- {position.text.strip()} {_source_citation(position.source_ids, links)}"
            for position in item.positions
        )
        for item in document.disagreements
    ]
    if disagreement_groups:
        disagreements = "\n\n".join(disagreement_groups)
    elif profile.language_profile == "default-ja":
        disagreements = "明示的な相違・対立は確認できません。"
    else:
        disagreements = "No explicit material disagreement was identified."
    if document.source_specific_insights:
        source_specific = "\n".join(
            f"- {item.insight.strip()} {_source_citation([item.source_id], links)}"
            for item in document.source_specific_insights
        )
    elif profile.language_profile == "default-ja":
        source_specific = "各ソースだけに固有の重要な知見は確認できません。"
    else:
        source_specific = "No material source-specific insight was identified."
    return render_comparison_template(
        template,
        {
            "frontmatter": "\n".join(frontmatter_lines),
            "title": source_set.title,
            "cover": f"![]({source_set.cover})\n\n" if source_set.cover else "",
            "summary": document.summary.strip(),
            "common_concepts": common_concepts,
            "perspectives": perspectives,
            "disagreements": disagreements,
            "source_specific_insights": source_specific,
            "technical_terms": "\n".join(f"- {term.strip()}" for term in document.technical_terms),
            "conclusion": document.conclusion.strip(),
            "sources": "\n".join(
                f"- [{entry.id} · {_markdown_label(entry.document.title)}]"
                f"({_source_link(entry.document.path, output_path)})"
                + (
                    f" — reviewStatus: {entry.document.review_status}"
                    if entry.document.review_status else ""
                )
                for entry in source_set.sources
            ),
        },
    )


def summary_metadata(path: Path) -> dict[str, Any]:
    metadata, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    return metadata
