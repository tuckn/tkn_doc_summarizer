from __future__ import annotations

from pathlib import Path

import pytest

from doc_summarizer.source import normalize_url, resolve_source


def _write_clip(path: Path, *, url: str, title: str = "Sample") -> None:
    path.write_text(
        "---\n"
        "type: webClip\n"
        f"title: {title}\n"
        f"url: {url}\n"
        "cliptool: Obsidian Web Clipper\n"
        "date: 2026-07-30T08:00:00+09:00\n"
        "---\n\n"
        "# Heading\n\nSource facts.",
        encoding="utf-8",
    )


def test_file_source_extracts_frontmatter_and_body(tmp_path: Path) -> None:
    source_path = tmp_path / "source.md"
    _write_clip(source_path, url="https://example.com/article", title="Article")
    source = resolve_source(
        str(source_path),
        source_roots=[],
        max_input_bytes=100_000,
    )
    assert source.title == "Article"
    assert source.url == "https://example.com/article"
    assert source.content.startswith("# Heading")
    assert len(source.source_sha256) == 64


def test_url_resolves_existing_clipped_markdown(tmp_path: Path) -> None:
    source_path = tmp_path / "clip.md"
    _write_clip(
        source_path,
        url="https://Example.com/article/?utm_source=test&b=2&a=1",
    )
    source = resolve_source(
        "https://example.com/article?a=1&b=2",
        source_roots=[tmp_path],
        max_input_bytes=100_000,
    )
    assert source.path == source_path.resolve()


def test_url_requires_local_clip(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no clipped Markdown"):
        resolve_source(
            "https://example.com/missing",
            source_roots=[tmp_path],
            max_input_bytes=100_000,
        )


def test_duplicate_url_fails(tmp_path: Path) -> None:
    _write_clip(tmp_path / "one.md", url="https://example.com/a")
    _write_clip(tmp_path / "two.md", url="https://example.com/a")
    with pytest.raises(ValueError, match="multiple clipped"):
        resolve_source(
            "https://example.com/a",
            source_roots=[tmp_path],
            max_input_bytes=100_000,
        )


def test_max_input_size_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "large.txt"
    path.write_text("x" * 100, encoding="utf-8")
    with pytest.raises(ValueError, match="max_input_bytes"):
        resolve_source(str(path), source_roots=[], max_input_bytes=10)


def test_normalize_url_rejects_non_web_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        normalize_url("file:///tmp/a.md")
