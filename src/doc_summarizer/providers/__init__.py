"""Configured summary provider adapters."""

from doc_summarizer.providers.base import (
    ComparisonProvider,
    ComparisonProviderResult,
    ProviderExecutionError,
    ProviderResult,
    SummaryProvider,
)
from doc_summarizer.providers.bridge import BridgeComparisonProvider, BridgeProvider

__all__ = [
    "BridgeComparisonProvider",
    "BridgeProvider",
    "ComparisonProvider",
    "ComparisonProviderResult",
    "ProviderExecutionError",
    "ProviderResult",
    "SummaryProvider",
]
