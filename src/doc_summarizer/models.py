"""Strict models used at the provider and pipeline boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentSource(StrictModel):
    path: Path
    title: str
    url: str | None = None
    cover: str | None = None
    published: str | None = None
    content: str
    source_sha256: str
    source_size_bytes: int = Field(default=0, ge=0)
    review_status: str | None = None


class SummaryRequest(StrictModel):
    source: DocumentSource
    prompt_envelope_version: str
    conversation_date: str | None = None
    context: str | None = None


class SeriesSource(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    document: DocumentSource


class DocumentSourceSet(StrictModel):
    source_set_id: str
    title: str = Field(min_length=1)
    mode: Literal["series", "compare"]
    cover: str | None = None
    published: str | None = None
    sources: list[SeriesSource] = Field(min_length=2)
    source_set_sha256: str
    conversation_date: str | None = None


class SeriesSummaryRequest(StrictModel):
    source_set: DocumentSourceSet
    prompt_envelope_version: str
    context: str | None = None


SummaryGenerationRequest = SummaryRequest | SeriesSummaryRequest


class ComparisonRequest(StrictModel):
    source_set: DocumentSourceSet
    prompt_envelope_version: str
    context: str | None = None


class ComparisonPoint(StrictModel):
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class CommonConcept(ComparisonPoint):
    source_ids: list[str] = Field(min_length=2)


class ComparisonPerspective(StrictModel):
    heading: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class ComparisonPosition(StrictModel):
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class ComparisonDisagreement(StrictModel):
    topic: str = Field(min_length=1)
    positions: list[ComparisonPosition] = Field(min_length=2)


class SourceSpecificInsight(StrictModel):
    source_id: str = Field(min_length=1)
    insight: str = Field(min_length=1)


class ComparisonDocument(StrictModel):
    title: str = Field(
        min_length=1,
        description="A concise title derived from the complete comparison",
    )
    description: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    common_concepts: list[CommonConcept] = Field(min_length=1)
    perspectives: list[ComparisonPerspective] = Field(min_length=1)
    disagreements: list[ComparisonDisagreement]
    source_specific_insights: list[SourceSpecificInsight]
    technical_terms: list[str] = Field(min_length=1)
    conclusion: str = Field(min_length=1)


class SummarySubsection(StrictModel):
    heading: str = Field(min_length=1)
    details: list[str] = Field(min_length=1)


class SummarySection(StrictModel):
    heading: str = Field(min_length=1)
    details: list[str] = Field(
        description="Direct details used only when a second heading level is unnecessary"
    )
    subsections: list[SummarySubsection] = Field(
        description="Optional H4-level groups below this major H3 section"
    )

    @model_validator(mode="after")
    def require_content(self) -> Self:
        if not self.details and not self.subsections:
            raise ValueError("a summary section must contain details or subsections")
        return self


class SummaryDocument(StrictModel):
    title: str = Field(
        min_length=1,
        description="A concise title derived from the complete summarized content",
    )
    summary: str = Field(
        min_length=1,
        description=(
            "One compact paragraph in the active summary profile's language that states "
            "the central thesis, essential reasoning, and result without duplicating the "
            "detailed structure"
        ),
    )
    structuring: list[SummarySection] = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    technical_terms: list[str] = Field(
        min_length=1,
        description=(
            "Important terms formatted as Markdown strings in the form "
            "'**term**: one or two source-grounded explanatory sentences'"
        ),
    )
    conclusion: str = Field(min_length=1)


class ConversationEvidence(StrictModel):
    source_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    start: str | None = Field(pattern=r"^[0-9]{2,}:[0-5][0-9]:[0-5][0-9]$")
    end: str | None = Field(pattern=r"^[0-9]{2,}:[0-5][0-9]:[0-5][0-9]$")
    speaker_label: str | None = Field(min_length=1, pattern=r"^[^\[\]\r\n]+$")


class ConversationItem(StrictModel):
    text: str = Field(min_length=1)
    kind: Literal["statement", "hearsay", "joke", "speculation", "wish", "plan", "commitment"]
    subject: str = Field(min_length=1, description="Who or what the statement concerns")
    speaker_name: str | None = Field(min_length=1)
    identity_status: Literal["unknown", "inferred", "confirmed"]
    identity_basis: str = Field(min_length=1)
    uncertainty: str = Field(min_length=1)
    evidence: list[ConversationEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def check_identity(self) -> Self:
        if (self.identity_status == "unknown") != (self.speaker_name is None):
            raise ValueError("unknown identity requires null name; named identities need a status")
        return self


class ConversationTopic(StrictModel):
    heading: str = Field(min_length=1)
    items: list[ConversationItem] = Field(min_length=1)


class ConversationDocument(StrictModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1, description="Short overview of topics, without analysis")
    topics: list[ConversationTopic] = Field(min_length=1)
    plans: list[ConversationItem]
    unconfirmed: list[ConversationItem]
    limitations: list[str] = Field(min_length=1)


class MeetingPoint(StrictModel):
    text: str = Field(min_length=1)
    basis: Literal["statement", "document", "context", "interpretation"]
    certainty: Literal["confirmed", "provisional", "needs-confirmation"]
    source_ids: list[str]


class MeetingTopic(StrictModel):
    heading: str = Field(min_length=1)
    items: list[MeetingPoint] = Field(min_length=1)


class RaidItem(MeetingPoint):
    category: Literal["Risk", "Action", "Issue", "Decision"]
    owner: str = Field(min_length=1)
    deadline: str = Field(min_length=1)
    status: str = Field(min_length=1)


class MeetingMinutesDocument(StrictModel):
    title: str = Field(min_length=1)
    summary: list[MeetingPoint] = Field(min_length=1)
    facts: list[MeetingTopic]
    open_questions: list[MeetingPoint]
    raid: list[RaidItem]
    next_checks: list[MeetingPoint]
    limitations: list[str] = Field(min_length=1)


GeneratedSummaryDocument = SummaryDocument | ConversationDocument | MeetingMinutesDocument


class SummaryResult(StrictModel):
    path: Path
    source_path: Path
    status: str
    report_path: Path | None = None
    details: dict[str, object] = Field(default_factory=dict)
