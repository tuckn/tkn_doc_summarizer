from __future__ import annotations

from pathlib import Path

import pytest

from doc_summarizer.config import AppConfig
from doc_summarizer.models import (
    SummaryDocument,
    SummaryGenerationRequest,
    SummarySection,
    SummarySubsection,
)
from doc_summarizer.notes import path_to_file_uri
from doc_summarizer.pipeline import summarize, synthesize_series
from doc_summarizer.prompting import load_summary_prompt
from doc_summarizer.providers.base import ProviderResult
from doc_summarizer.source import split_frontmatter
from doc_summarizer.summary_resources import load_summary_profile
from doc_summarizer.validation import validate_summary


class FakeProvider:
    def __init__(self, profile_name: str = "default-ja") -> None:
        self.prompt = load_summary_prompt(profile_name=profile_name)
        self.profile = load_summary_profile(profile_name, prompt=self.prompt)
        self.calls = 0

    def generate(self, request: SummaryGenerationRequest) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            document=SummaryDocument(
                title="AI-generated complete summary",
                description="This is a source-grounded description.",
                summary="This is the complete summary.",
                structuring=[
                    SummarySection(
                        heading="Main topic",
                        details=[],
                        subsections=[
                            SummarySubsection(
                                heading="Supporting detail",
                                details=["The source provides one important fact."],
                            )
                        ],
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
        summary_profile=profile_name,
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


def _series_sources(tmp_path: Path) -> list[Path]:
    first = tmp_path / "part-1.md"
    first.write_text(
        "---\ntitle: Example article 1\ncover: https://example.com/cover.png\n"
        "published: 2026-08-01\n---\n\n# Part 1\n\nFirst fact.",
        encoding="utf-8",
    )
    second = tmp_path / "part-2.md"
    second.write_text("# Part 2\n\nSecond fact and conclusion.", encoding="utf-8")
    return [first, second]


def test_create_validate_and_idempotent_rerun(tmp_path: Path) -> None:
    source = _source(tmp_path)
    provider = FakeProvider()
    first = summarize(str(source), _config(tmp_path), provider=provider)
    assert first.status == "created"
    assert first.report_path is not None
    assert not validate_summary(first.path)
    assert provider.calls == 1
    text = first.path.read_text(encoding="utf-8")
    metadata, _ = split_frontmatter(text)
    assert metadata["type"] == "summary"
    assert metadata["schemaVersion"] == "5.0"
    assert metadata["promptVersion"] == "3.0"
    assert metadata["summaryProfile"] == "default-ja"
    assert metadata["source"] == str(source.resolve())
    assert f"source: '{source.resolve()}'" in text
    assert metadata["summaryProfileSha256"] == provider.profile.sha256
    assert metadata["outputSchemaSha256"] == provider.profile.schema.sha256
    assert metadata["templateId"] == provider.profile.template.template_id
    assert metadata["templateVersion"] == provider.profile.template.version
    assert metadata["templateSha256"] == provider.profile.template.sha256
    assert "nouns" not in metadata
    assert "requestedModel" not in metadata
    assert 'schemaVersion: "5.0"' in text
    assert 'promptVersion: "3.0"' in text
    assert (
        text.index("# Example article")
        < text.index("![](https://example.com/cover.png)")
        < text.index("## 1. 要約")
    )
    assert "_default-ja_" in first.path.name
    assert "### Main topic" in text
    assert "#### Supporting detail" in text

    second = summarize(str(source), _config(tmp_path), provider=provider)
    assert second.status == "unchanged"
    assert provider.calls == 1


def test_create_validate_and_idempotent_series_summary(tmp_path: Path) -> None:
    sources = _series_sources(tmp_path)
    provider = FakeProvider()

    first = synthesize_series(
        [str(path) for path in sources],
        _config(tmp_path),
        title="Complete example article",
        provider=provider,
    )

    assert first.status == "created"
    assert first.source_path == sources[0]
    assert first.details["source_count"] == 2
    assert not validate_summary(first.path)
    metadata, _ = split_frontmatter(first.path.read_text(encoding="utf-8"))
    assert metadata["schemaVersion"] == "6.0"
    assert metadata["synthesisMode"] == "series"
    assert metadata["title"] == "Complete example article"
    assert len(metadata["sourceSetId"]) == 36
    assert [entry["id"] for entry in metadata["sources"]] == ["S1", "S2"]
    assert [entry["source"] for entry in metadata["sources"]] == [
        str(path.resolve()) for path in sources
    ]
    assert f"    source: '{sources[0].resolve()}'" in first.path.read_text(encoding="utf-8")
    assert len(metadata["sourceSetSha256"]) == 64
    assert provider.calls == 1

    second = synthesize_series(
        [str(path) for path in sources],
        _config(tmp_path),
        title="Complete example article",
        provider=provider,
    )
    assert second.status == "unchanged"
    assert provider.calls == 1


def test_legacy_file_uri_source_reference_remains_current(tmp_path: Path) -> None:
    source = _source(tmp_path)
    provider = FakeProvider()
    first = summarize(str(source), _config(tmp_path), provider=provider)
    text = first.path.read_text(encoding="utf-8")
    text = text.replace(
        f"source: '{source.resolve()}'",
        f'source: "{path_to_file_uri(source)}"',
    )
    first.path.write_text(text, encoding="utf-8")

    assert not validate_summary(first.path)
    file_uri_config = _config(tmp_path).model_copy(update={"source_path_format": "file-uri"})
    second = summarize(str(source), file_uri_config, provider=provider)
    assert second.status == "unchanged"
    assert second.path == first.path
    assert provider.calls == 1


def test_legacy_series_file_uri_references_remain_valid(tmp_path: Path) -> None:
    sources = _series_sources(tmp_path)
    provider = FakeProvider()
    result = synthesize_series(
        [str(path) for path in sources],
        _config(tmp_path),
        title="Complete example article",
        provider=provider,
    )
    text = result.path.read_text(encoding="utf-8")
    for source in sources:
        text = text.replace(
            f"source: '{source.resolve()}'",
            f'source: "{path_to_file_uri(source)}"',
        )
    result.path.write_text(text, encoding="utf-8")

    assert not validate_summary(result.path)

    file_uri_config = _config(tmp_path).model_copy(update={"source_path_format": "file-uri"})
    second = synthesize_series(
        [str(path) for path in sources],
        file_uri_config,
        title="Complete example article",
        provider=provider,
    )

    assert second.status == "unchanged"
    assert second.path == result.path
    assert provider.calls == 1


def test_file_uri_config_writes_file_uri_and_requires_overwrite_to_convert(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    provider = FakeProvider()
    native_config = _config(tmp_path)
    file_uri_config = native_config.model_copy(update={"source_path_format": "file-uri"})
    summarize(str(source), native_config, provider=provider)

    with pytest.raises(RuntimeError, match="explicit --overwrite"):
        summarize(str(source), file_uri_config, provider=provider)

    updated = summarize(
        str(source),
        file_uri_config,
        provider=provider,
        overwrite=True,
    )
    text = updated.path.read_text(encoding="utf-8")
    metadata, _ = split_frontmatter(text)
    assert updated.status == "updated"
    assert metadata["source"] == path_to_file_uri(source)
    assert f'source: "{path_to_file_uri(source)}"' in text
    assert provider.calls == 2


def test_series_file_uri_config_writes_file_uri_sources(tmp_path: Path) -> None:
    sources = _series_sources(tmp_path)
    provider = FakeProvider()
    config = _config(tmp_path).model_copy(update={"source_path_format": "file-uri"})

    result = synthesize_series(
        [str(path) for path in sources],
        config,
        title="Complete example article",
        provider=provider,
    )

    metadata, _ = split_frontmatter(result.path.read_text(encoding="utf-8"))
    assert [entry["source"] for entry in metadata["sources"]] == [
        path_to_file_uri(path) for path in sources
    ]
    assert result.details["source_path_format"] == "file-uri"


def test_series_uses_generated_title_when_title_is_omitted(tmp_path: Path) -> None:
    sources = _series_sources(tmp_path)
    provider = FakeProvider()

    first = synthesize_series(
        [str(path) for path in sources],
        _config(tmp_path),
        provider=provider,
    )

    metadata, body = split_frontmatter(first.path.read_text(encoding="utf-8"))
    assert metadata["title"] == "AI-generated complete summary"
    assert body.lstrip().startswith("# AI-generated complete summary\n")
    assert "AI-generated complete summary" in first.path.name

    second = synthesize_series(
        [str(path) for path in sources],
        _config(tmp_path),
        provider=provider,
    )
    assert second.status == "unchanged"
    assert second.path == first.path
    assert provider.calls == 1


def test_series_dry_run_marks_generated_title_as_pending(tmp_path: Path) -> None:
    sources = _series_sources(tmp_path)
    provider = FakeProvider()

    result = synthesize_series(
        [str(path) for path in sources],
        _config(tmp_path),
        provider=provider,
        dry_run=True,
    )

    assert result.status == "planned"
    assert result.details["generated_title_pending"] is True
    assert provider.calls == 0


def test_changed_series_source_requires_overwrite(tmp_path: Path) -> None:
    sources = _series_sources(tmp_path)
    provider = FakeProvider()
    first = synthesize_series(
        [str(path) for path in sources],
        _config(tmp_path),
        title="Complete example article",
        provider=provider,
    )
    second_source = tmp_path / "part-2.md"
    second_source.write_text(
        second_source.read_text(encoding="utf-8") + "\nUpdated.",
        encoding="utf-8",
    )

    assert validate_summary(first.path) == ["sources[2].sourceSha256 does not match its source"]

    with pytest.raises(RuntimeError, match="explicit --overwrite"):
        synthesize_series(
            [str(path) for path in sources],
            _config(tmp_path),
            title="Complete example article",
            provider=provider,
        )

    assert first.path.exists()
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


def test_japanese_and_english_profiles_create_side_by_side(tmp_path: Path) -> None:
    source = _source(tmp_path)
    japanese = summarize(
        str(source),
        _config(tmp_path, "default-ja"),
        provider=FakeProvider("default-ja"),
    )
    english = summarize(
        str(source),
        _config(tmp_path, "default-en"),
        provider=FakeProvider("default-en"),
    )

    assert japanese.path != english.path
    assert "_default-ja_" in japanese.path.name
    assert "_default-en_" in english.path.name
    assert "## 1. 要約" in japanese.path.read_text(encoding="utf-8")
    assert "## 1. Summary" in english.path.read_text(encoding="utf-8")


def test_same_custom_prompt_can_coexist_across_profiles(tmp_path: Path) -> None:
    source = _source(tmp_path)
    custom_path = tmp_path / "custom.md"
    custom_path.write_text(
        "---\n"
        "type: prompt\n"
        "id: c7aa8da6-263e-454d-80e7-b320578bea95\n"
        'version: "1.0"\n'
        "---\n\n"
        "Custom instructions.\n",
        encoding="utf-8",
    )
    custom_prompt = load_summary_prompt(custom_path)
    japanese_provider = FakeProvider("default-ja")
    japanese_provider.prompt = custom_prompt
    japanese_provider.profile = load_summary_profile("default-ja", prompt=custom_prompt)
    english_provider = FakeProvider("default-en")
    english_provider.prompt = custom_prompt
    english_provider.profile = load_summary_profile("default-en", prompt=custom_prompt)

    japanese = summarize(
        str(source),
        _config(tmp_path, "default-ja"),
        provider=japanese_provider,
    )
    english = summarize(
        str(source),
        _config(tmp_path, "default-en"),
        provider=english_provider,
    )

    assert japanese.path != english.path
    assert japanese_provider.prompt.prompt_id == english_provider.prompt.prompt_id


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


def test_summary_section_requires_direct_details_or_subsections() -> None:
    with pytest.raises(ValueError, match="must contain details or subsections"):
        SummarySection(heading="Empty", details=[], subsections=[])


def test_current_summary_requires_cover_image(tmp_path: Path) -> None:
    result = summarize(str(_source(tmp_path)), _config(tmp_path), provider=FakeProvider())
    text = result.path.read_text(encoding="utf-8").replace(
        "![](https://example.com/cover.png)\n\n",
        "",
        1,
    )
    result.path.write_text(text, encoding="utf-8")

    assert validate_summary(result.path) == ["summary body must contain the cover image"]


@pytest.mark.parametrize(
    ("schema_version", "remove_cover"),
    [("2.0", True), ("3.0", False)],
)
def test_existing_summary_schema_remains_valid(
    tmp_path: Path,
    schema_version: str,
    remove_cover: bool,
) -> None:
    result = summarize(str(_source(tmp_path)), _config(tmp_path), provider=FakeProvider())
    profile_fields = {
        "summaryProfile",
        "summaryProfileSha256",
        "outputSchemaSha256",
        "templateId",
        "templateVersion",
        "templateSha256",
    }
    text = result.path.read_text(encoding="utf-8")
    text = "\n".join(
        line for line in text.splitlines() if line.partition(":")[0] not in profile_fields
    )
    text = text.replace('schemaVersion: "4.0"', f'schemaVersion: "{schema_version}"')
    text = text.replace('schemaVersion: "5.0"', f'schemaVersion: "{schema_version}"')
    text = (
        text.replace("## 1. 要約", "## 1. Summary")
        .replace("## 2. 構造化（抽象から具体へ）", "## 2. Structuring (from abstract to concrete)")
        .replace("## 3. 重要ポイント", "## 3. Key points")
        .replace("## 4. 専門用語", "## 4. Technical terms")
        .replace("## 5. 結論", "## 5. Conclusion")
    )
    if remove_cover:
        text = text.replace("![](https://example.com/cover.png)\n\n", "", 1)
    result.path.write_text(text, encoding="utf-8")

    assert validate_summary(result.path) == []


def test_existing_schema_4_summary_remains_valid(tmp_path: Path) -> None:
    result = summarize(str(_source(tmp_path)), _config(tmp_path), provider=FakeProvider())
    text = (
        result.path.read_text(encoding="utf-8")
        .replace('schemaVersion: "5.0"', 'schemaVersion: "4.0"')
        .replace("## 1. 要約", "## 1. Summary")
        .replace("## 2. 構造化（抽象から具体へ）", "## 2. Structuring (from abstract to concrete)")
        .replace("## 3. 重要ポイント", "## 3. Key points")
        .replace("## 4. 専門用語", "## 4. Technical terms")
        .replace("## 5. 結論", "## 5. Conclusion")
    )
    result.path.write_text(text, encoding="utf-8")

    assert validate_summary(result.path) == []


def test_explicit_output_collision_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    output = tmp_path / "manual.md"
    output.write_text("# User file", encoding="utf-8")
    with pytest.raises(RuntimeError, match="another source, summary profile, or prompt"):
        summarize(
            str(source),
            _config(tmp_path),
            provider=FakeProvider(),
            explicit_output=output,
            overwrite=True,
        )
