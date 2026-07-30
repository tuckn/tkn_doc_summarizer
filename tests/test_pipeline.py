from __future__ import annotations

from pathlib import Path

import pytest

from doc_summarizer.config import AppConfig
from doc_summarizer.models import (
    SummaryDocument,
    SummaryRequest,
    SummarySection,
)
from doc_summarizer.pipeline import summarize
from doc_summarizer.prompting import PROMPT_ENVELOPE_VERSION, load_summary_prompt
from doc_summarizer.providers.base import ProviderResult
from doc_summarizer.source import split_frontmatter
from doc_summarizer.validation import validate_summary


class FakeProvider:
    def __init__(self) -> None:
        self.prompt = load_summary_prompt()
        self.calls = 0

    def generate(self, request: SummaryRequest) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            document=SummaryDocument(
                description="This is a source-grounded description.",
                summary="This is the complete summary.",
                structuring=[
                    SummarySection(
                        heading="Main topic",
                        details=["The source provides one important fact."],
                    )
                ],
                key_points=["The important fact is retained."],
                technical_terms=["**Term**: The meaning used in the source."],
                conclusion="The source reaches a supported conclusion.",
            ),
            provider="fake",
            model="fake-model",
            generator="Fake (fake-model)",
            provider_version="1.0",
            prompt_id=self.prompt.prompt_id,
            prompt_version=self.prompt.version,
            prompt_envelope_version=PROMPT_ENVELOPE_VERSION,
            prompt_source=self.prompt.source,
            prompt_sha256=self.prompt.sha256,
        )


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        source_roots=[],
        output_root=tmp_path / "summaries",
        reports_root=tmp_path / "reports",
        provider="codex",
        model=None,
        codex_executable="codex",
        codex_timeout_seconds=60,
        max_input_bytes=100_000,
        summary_prompt=None,
    )


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "source.md"
    path.write_text(
        "---\n"
        "title: Example article\n"
        "url: https://example.com/article\n"
        "cover: https://example.com/cover.png\n"
        "published: 2026-07-29\n"
        "---\n\n"
        "# Example article\n\nA fact and its explanation.",
        encoding="utf-8",
    )
    return path


def test_create_validate_and_idempotent_rerun(tmp_path: Path) -> None:
    source = _source(tmp_path)
    provider = FakeProvider()
    first = summarize(str(source), _config(tmp_path), provider=provider)
    assert first.status == "created"
    assert first.report_path is not None
    assert not validate_summary(first.path)
    assert provider.calls == 1

    second = summarize(str(source), _config(tmp_path), provider=provider)
    assert second.status == "unchanged"
    assert provider.calls == 1


def test_dry_run_has_no_provider_call_or_writes(tmp_path: Path) -> None:
    source = _source(tmp_path)
    provider = FakeProvider()
    result = summarize(
        str(source),
        _config(tmp_path),
        provider=provider,
        dry_run=True,
    )
    assert result.status == "planned"
    assert provider.calls == 0
    assert not result.path.exists()
    assert not (tmp_path / "reports").exists()


def test_changed_source_requires_overwrite(tmp_path: Path) -> None:
    source = _source(tmp_path)
    provider = FakeProvider()
    first = summarize(str(source), _config(tmp_path), provider=provider)
    source.write_text(source.read_text(encoding="utf-8") + "\nChanged.", encoding="utf-8")

    with pytest.raises(RuntimeError, match="explicit --overwrite"):
        summarize(str(source), _config(tmp_path), provider=provider)
    assert first.path.exists()
    assert provider.calls == 1


def test_overwrite_preserves_identity_and_resets_review(tmp_path: Path) -> None:
    source = _source(tmp_path)
    provider = FakeProvider()
    first = summarize(str(source), _config(tmp_path), provider=provider)
    original_text = first.path.read_text(encoding="utf-8")
    original_metadata, _ = split_frontmatter(original_text)
    first.path.write_text(
        original_text.replace("reviewStatus: unreviewed", "reviewStatus: accepted"),
        encoding="utf-8",
    )

    updated = summarize(
        str(source),
        _config(tmp_path),
        provider=provider,
        overwrite=True,
    )

    metadata, _ = split_frontmatter(updated.path.read_text(encoding="utf-8"))
    assert updated.status == "updated"
    assert metadata["noteId"] == original_metadata["noteId"]
    assert metadata["date"] == original_metadata["date"]
    assert metadata["reviewStatus"] == "unreviewed"


def test_explicit_output_collision_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "manual.md"
    output.write_text("# User file", encoding="utf-8")
    with pytest.raises(RuntimeError, match="another source or prompt"):
        summarize(
            str(source),
            _config(tmp_path),
            provider=FakeProvider(),
            explicit_output=output,
            overwrite=True,
        )
