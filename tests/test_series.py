from __future__ import annotations

from pathlib import Path

import pytest

from doc_summarizer.models import SeriesSummaryRequest
from doc_summarizer.prompting import (
    SERIES_PROMPT_ENVELOPE_VERSION,
    load_summary_prompt,
    render_summary_prompt,
)
from doc_summarizer.series import resolve_series_sources


def test_series_preserves_cli_order_and_generates_stable_identity(tmp_path: Path) -> None:
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    first.write_text("# One\n\nFirst.", encoding="utf-8")
    second.write_text("# Two\n\nSecond.", encoding="utf-8")

    source_set = resolve_series_sources(
        [str(first), str(second)],
        title="Complete article",
        source_roots=[],
        max_input_bytes=1_000,
        max_total_input_bytes=2_000,
    )
    rerun = resolve_series_sources(
        [str(first), str(second)],
        title="Complete article",
        source_roots=[],
        max_input_bytes=1_000,
        max_total_input_bytes=2_000,
    )

    assert [entry.id for entry in source_set.sources] == ["S1", "S2"]
    assert [entry.document.path for entry in source_set.sources] == [
        first.resolve(),
        second.resolve(),
    ]
    assert source_set.title == "Complete article"
    assert source_set.source_set_id == rerun.source_set_id
    assert len(source_set.source_set_sha256) == 64

    reversed_set = resolve_series_sources(
        [str(second), str(first)],
        title="Complete article",
        source_roots=[],
        max_input_bytes=1_000,
        max_total_input_bytes=2_000,
    )
    assert reversed_set.source_set_id != source_set.source_set_id

    second.write_text("# Two\n\nChanged second page.", encoding="utf-8")
    changed = resolve_series_sources(
        [str(first), str(second)],
        title="Complete article",
        source_roots=[],
        max_input_bytes=1_000,
        max_total_input_bytes=2_000,
    )
    assert changed.source_set_id == source_set.source_set_id
    assert changed.source_set_sha256 != source_set.source_set_sha256

    rendered = render_summary_prompt(
        load_summary_prompt(),
        SeriesSummaryRequest(
            source_set=source_set,
            prompt_envelope_version=SERIES_PROMPT_ENVELOPE_VERSION,
        ),
    )
    assert rendered.index("BEGIN_DOCUMENT 1 ID=S1") < rendered.index("BEGIN_DOCUMENT 2 ID=S2")
    assert "one integrated summary of the whole article" in rendered


def test_series_defaults_to_first_source_title(tmp_path: Path) -> None:
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    first.write_text("# Whole article\n\nFirst.", encoding="utf-8")
    second.write_text("# Part two\n\nSecond.", encoding="utf-8")

    source_set = resolve_series_sources(
        [str(first), str(second)],
        title=None,
        source_roots=[],
        max_input_bytes=1_000,
        max_total_input_bytes=2_000,
    )

    assert source_set.title == "Whole article"


def test_series_requires_at_least_two_sources(tmp_path: Path) -> None:
    source = tmp_path / "one.md"
    source.write_text("# One\n\nFirst.", encoding="utf-8")

    with pytest.raises(ValueError, match="at least two"):
        resolve_series_sources(
            [str(source)],
            title=None,
            source_roots=[],
            max_input_bytes=1_000,
            max_total_input_bytes=2_000,
        )


def test_series_rejects_duplicate_local_source(tmp_path: Path) -> None:
    source = tmp_path / "one.md"
    source.write_text("# One\n\nFirst.", encoding="utf-8")

    with pytest.raises(ValueError, match="same local source"):
        resolve_series_sources(
            [str(source), str(source)],
            title=None,
            source_roots=[],
            max_input_bytes=1_000,
            max_total_input_bytes=2_000,
        )


def test_series_enforces_total_input_size(tmp_path: Path) -> None:
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    first.write_text("x" * 20, encoding="utf-8")
    second.write_text("y" * 20, encoding="utf-8")

    with pytest.raises(ValueError, match="max_total_input_bytes"):
        resolve_series_sources(
            [str(first), str(second)],
            title=None,
            source_roots=[],
            max_input_bytes=1_000,
            max_total_input_bytes=30,
        )
