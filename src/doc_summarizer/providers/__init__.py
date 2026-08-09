"""Configured summary provider adapters."""

from doc_summarizer.providers.base import (
    ComparisonProvider,
    ComparisonProviderResult,
    ProviderResult,
    SummaryProvider,
)
from doc_summarizer.providers.codex import CodexProvider
from doc_summarizer.providers.comparison import CodexComparisonProvider

__all__ = [
    "CodexComparisonProvider",
    "CodexProvider",
    "ComparisonProvider",
    "ComparisonProviderResult",
    "ProviderResult",
    "SummaryProvider",
]
