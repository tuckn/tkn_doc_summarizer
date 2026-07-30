"""Strict models used at the provider and pipeline boundaries."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


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


class SummaryRequest(StrictModel):
    source: DocumentSource
    prompt_envelope_version: str


class SummarySection(StrictModel):
    heading: str = Field(min_length=1)
    details: list[str] = Field(min_length=1)


class SummaryDocument(StrictModel):
    description: str = Field(min_length=1)
    summary: str = Field(min_length=1)
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
