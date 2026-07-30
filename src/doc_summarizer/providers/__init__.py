"""Configured summary provider adapters."""

from doc_summarizer.providers.base import ProviderResult, SummaryProvider
from doc_summarizer.providers.codex import CodexProvider

__all__ = ["CodexProvider", "ProviderResult", "SummaryProvider"]
