"""Summary provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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
    generation_record: dict[str, Any] | None = None


class SummaryProvider(Protocol):
    prompt: SummaryPrompt
    profile: SummaryProfile

    def plan(self, request: SummaryGenerationRequest | None = None) -> dict[str, Any]: ...

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
    generation_record: dict[str, Any] | None = None


class ComparisonProvider(Protocol):
    prompt: SummaryPrompt
    profile: ComparisonProfile

    def plan(self, request: ComparisonRequest | None = None) -> dict[str, Any]: ...

    def generate(self, request: ComparisonRequest) -> ComparisonProviderResult: ...


class ProviderExecutionError(RuntimeError):
    """Content-free Bridge failure plus its structured execution record."""

    def __init__(self, message: str, *, error_details: dict[str, Any]) -> None:
        super().__init__(message)
        self.error_details = error_details
