"""Summary provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from doc_summarizer.comparison_resources import ComparisonProfile
from doc_summarizer.models import (
    ComparisonDocument,
    ComparisonRequest,
    SummaryDocument,
    SummaryGenerationRequest,
)
from doc_summarizer.prompting import SummaryPrompt
from doc_summarizer.summary_resources import SummaryProfile


@dataclass(frozen=True)
class ProviderResult:
    document: SummaryDocument
    provider: str
    model: str | None
    generator: str
    provider_version: str | None
    prompt_id: str
    prompt_version: str
    prompt_envelope_version: str
    prompt_source: str
    prompt_sha256: str


class SummaryProvider(Protocol):
    prompt: SummaryPrompt
    profile: SummaryProfile

    def generate(self, request: SummaryGenerationRequest) -> ProviderResult: ...


@dataclass(frozen=True)
class ComparisonProviderResult:
    document: ComparisonDocument
    provider: str
    model: str | None
    generator: str
    provider_version: str | None
    prompt_id: str
    prompt_version: str
    prompt_envelope_version: str
    prompt_source: str
    prompt_sha256: str


class ComparisonProvider(Protocol):
    prompt: SummaryPrompt
    profile: ComparisonProfile

    def generate(self, request: ComparisonRequest) -> ComparisonProviderResult: ...
