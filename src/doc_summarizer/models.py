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


class SummaryRequest(StrictModel):
    source: DocumentSource
    prompt_envelope_version: str


class SeriesSource(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    document: DocumentSource


class DocumentSourceSet(StrictModel):
    source_set_id: str
    title: str = Field(min_length=1)
    mode: Literal["series"]
    cover: str | None = None
    published: str | None = None
    sources: list[SeriesSource] = Field(min_length=2)
    source_set_sha256: str


class SeriesSummaryRequest(StrictModel):
    source_set: DocumentSourceSet
    prompt_envelope_version: str


SummaryGenerationRequest = SummaryRequest | SeriesSummaryRequest


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
    description: str = Field(min_length=1)
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


class SummaryResult(StrictModel):
    path: Path
    source_path: Path
    status: str
    report_path: Path | None = None
    details: dict[str, object] = Field(default_factory=dict)
