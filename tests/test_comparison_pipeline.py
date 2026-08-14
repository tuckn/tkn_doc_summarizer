from __future__ import annotations

from pathlib import Path

import pytest

from doc_summarizer.comparison_resources import load_comparison_profile
from doc_summarizer.config import AppConfig
from doc_summarizer.models import (
    CommonConcept,
    ComparisonDocument,
    ComparisonPerspective,
    ComparisonRequest,
    SourceSpecificInsight,
)
from doc_summarizer.notes import path_to_file_uri
from doc_summarizer.pipeline import synthesize_compare
from doc_summarizer.providers.base import ComparisonProviderResult
from doc_summarizer.source import split_frontmatter
from doc_summarizer.validation import validate_summary


class FakeComparisonProvider:
    def __init__(self, profile_name: str = "default-ja", *, invalid_source: bool = False) -> None:
        self.profile = load_comparison_profile(profile_name)
        self.prompt = self.profile.prompt
        self.invalid_source = invalid_source
        self.calls = 0

    def generate(self, request: ComparisonRequest) -> ComparisonProviderResult:
        self.calls += 1
        return ComparisonProviderResult(
            document=ComparisonDocument(
                title="AI生成による記事比較",
                description="2つの記事が共有する概念と異なる観点を比較したノート。",
                summary="両記事は共通概念を扱う一方、重点の置き方が異なる。",
                common_concepts=[
                    CommonConcept(text="両記事は共通概念を重視する。", source_ids=["S1", "S2"])
                ],
                perspectives=[
                    ComparisonPerspective(
                        heading="異なる重点",
                        explanation="一方は理論、他方は実務を重視する。",
                        source_ids=["S1", "S2"],
                    )
                ],
                disagreements=[],
                source_specific_insights=[
                    SourceSpecificInsight(
                        source_id="S9" if self.invalid_source else "S1",
                        insight="第一の記事だけが具体例を示す。",
                    )
                ],
                technical_terms=["**共通概念**: 複数のソースが支持する概念。"],
                conclusion="共通点を基盤にしつつ、観点の違いを区別して読む必要がある。",
            ),
            provider="fake",
            model="fake-model",
            generator="Fake (fake-model)",
            provider_version="1.0",
            prompt_id=self.prompt.prompt_id,
            prompt_version=self.prompt.version,
            prompt_envelope_version=request.prompt_envelope_version,
            prompt_source=self.prompt.source,
            prompt_sha256=self.prompt.sha256,
        )


def _config(tmp_path: Path, profile_name: str = "default-ja") -> AppConfig:
    return AppConfig(
        source_roots=[],
        output_root=tmp_path / "summaries",
        reports_root=tmp_path / "reports",
        provider="codex",
        model=None,
        codex_executable="codex",
        codex_timeout_seconds=60,
        max_input_bytes=100_000,
        max_total_input_bytes=200_000,
        summary_profile=profile_name,
        summary_prompt=None,
    )


def _sources(tmp_path: Path) -> list[Path]:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n\nShared concept and theoretical view.", encoding="utf-8")
    second.write_text("# Second\n\nShared concept and practical view.", encoding="utf-8")
    return [first, second]


def test_create_validate_and_idempotent_comparison(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    provider = FakeComparisonProvider()

    first = synthesize_compare(
        [str(path) for path in sources],
        _config(tmp_path),
        title="記事比較",
        provider=provider,
    )

    assert first.status == "created"
    assert not validate_summary(first.path)
    metadata, _ = split_frontmatter(first.path.read_text(encoding="utf-8"))
    assert metadata["schemaVersion"] == "7.0"
    assert metadata["synthesisMode"] == "compare"
    assert metadata["title"] == "記事比較"
    assert metadata["summaryProfile"] == "compare-ja"
    assert [entry["source"] for entry in metadata["sources"]] == [
        str(path.resolve()) for path in sources
    ]
    text = first.path.read_text(encoding="utf-8")
    assert "## 2. 共通概念" in text
    assert "両記事は共通概念を重視する。 [S1, S2]" in text
    assert "明示的な相違・対立は確認できません。" in text
    assert provider.calls == 1

    second = synthesize_compare(
        [str(path) for path in sources],
        _config(tmp_path),
        title="記事比較",
        provider=provider,
    )
    assert second.status == "unchanged"
    assert provider.calls == 1


def test_comparison_rejects_unknown_generated_source_id(tmp_path: Path) -> None:
    sources = _sources(tmp_path)

    with pytest.raises(RuntimeError, match="unknown source id: S9"):
        synthesize_compare(
            [str(path) for path in sources],
            _config(tmp_path),
            provider=FakeComparisonProvider(invalid_source=True),
        )


def test_comparison_uses_generated_title_when_title_is_omitted(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    provider = FakeComparisonProvider()

    first = synthesize_compare(
        [str(path) for path in sources],
        _config(tmp_path),
        provider=provider,
    )

    metadata, body = split_frontmatter(first.path.read_text(encoding="utf-8"))
    assert metadata["title"] == "AI生成による記事比較"
    assert body.lstrip().startswith("# AI生成による記事比較\n")

    second = synthesize_compare(
        [str(path) for path in sources],
        _config(tmp_path),
        provider=provider,
    )
    assert second.status == "unchanged"
    assert second.path == first.path
    assert provider.calls == 1


def test_english_comparison_profile_renders_english_sections(tmp_path: Path) -> None:
    sources = _sources(tmp_path)

    result = synthesize_compare(
        [str(path) for path in sources],
        _config(tmp_path, "default-en"),
        title="Article comparison",
        provider=FakeComparisonProvider("default-en"),
    )

    text = result.path.read_text(encoding="utf-8")
    assert "## 1. Comparison summary" in text
    assert "## 4. Differences and disagreements" in text
    assert not validate_summary(result.path)


def test_comparison_file_uri_config_writes_file_uri_sources(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    config = _config(tmp_path).model_copy(update={"source_path_format": "file-uri"})

    result = synthesize_compare(
        [str(path) for path in sources],
        config,
        title="記事比較",
        provider=FakeComparisonProvider(),
    )

    metadata, _ = split_frontmatter(result.path.read_text(encoding="utf-8"))
    assert [entry["source"] for entry in metadata["sources"]] == [
        path_to_file_uri(path) for path in sources
    ]
    assert result.details["source_path_format"] == "file-uri"


def test_comparison_rejects_custom_summary_prompt(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    prompt = tmp_path / "custom-prompt.md"
    prompt.write_text("---\nid: custom\nversion: '1.0'\n---\nCustom", encoding="utf-8")
    config = _config(tmp_path).model_copy(update={"summary_prompt": prompt})

    with pytest.raises(ValueError, match="not supported with --mode compare"):
        synthesize_compare(
            [str(path) for path in sources],
            config,
            provider=FakeComparisonProvider(),
        )
