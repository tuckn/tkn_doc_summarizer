from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from doc_summarizer.notes import frontmatter_timestamp, yaml_quote
from doc_summarizer.source import split_frontmatter
from doc_summarizer.yaml_format import load_metadata, normalize_yaml


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-07",
        "2026-10-07T01:02:03Z",
        "2026-10-07T01:02:03+09:00",
        "2026-10-07T01:02:03-05:30",
        "2026-10-07T01:02:03.123456789Z",
    ],
)
@pytest.mark.parametrize("style", ["", "'", '"'])
def test_dates_preserve_spelling_and_become_strings(value: str, style: str) -> None:
    text = f"custom: {style}{value}{style} # keep\nitems: [{style}{value}{style}, null, '']\n"
    result = normalize_yaml(text)
    assert f'custom: "{value}" # keep' in result
    assert yaml.safe_load(result) == {"custom": value, "items": [value, None, ""]}
    assert normalize_yaml(result) == result
    assert load_metadata(text)["custom"] == value


def test_windows_paths_and_urls() -> None:
    text = (
        "source: C:\\path\\user's notes\\file.md\n"
        "network: \\\\server\\share\\file.md\n"
        "forward: C:/path/to/file.md\n"
        "url: https://example.com/2026-10-07\n"
        "uri: file:///C:/path/to/file.md\n"
    )
    result = normalize_yaml(text)
    assert "source: 'C:\\path\\user''s notes\\file.md'" in result
    assert "network: '\\\\server\\share\\file.md'" in result
    assert "forward: 'C:/path/to/file.md'" in result
    assert "url: https://example.com/2026-10-07\n" in result
    assert "uri: file:///C:/path/to/file.md\n" in result
    assert load_metadata(result) == load_metadata(text)
    assert normalize_yaml(result) == result
    assert yaml_quote(r"C:\path\image.png") == "'C:\\path\\image.png'"
    assert yaml_quote("x://example/image.png") == '"x://example/image.png"'
    assert yaml_quote("file:///C:/path/to/image.png") == '"file:///C:/path/to/image.png"'


def test_rename_preserves_comments_order_crlf_and_fraction() -> None:
    text = "# keep\r\ndate: 2026-10-07T01:02:03.123456789Z # original\r\nupdated: null\r\n"
    result = normalize_yaml(text, rename_date=True)
    assert (
        result
        == '# keep\r\ncreated: "2026-10-07T01:02:03.123456789Z" # original\r\nupdated: null\r\n'
    )
    assert normalize_yaml(result, rename_date=True) == result


@pytest.mark.parametrize("text", ["date: a\ncreated: b\n", "date: a\ndate: b\n"])
def test_conflicts_are_not_overwritten(text: str) -> None:
    with pytest.raises(ValueError):
        normalize_yaml(text, rename_date=True)


def test_timestamp_tag_and_anchor() -> None:
    text = "custom: &when !!timestamp 2026-10-07T01:02:03.123456789Z\ncopy: *when\n"
    result = normalize_yaml(text)
    assert "!!timestamp" not in result
    assert yaml.safe_load(result)["copy"] == "2026-10-07T01:02:03.123456789Z"
    assert normalize_yaml(result) == result


def test_frontmatter_loading_does_not_change_yaml_global_loader() -> None:
    value = "2026-10-07T01:02:03.123456789Z"
    metadata, body = split_frontmatter(f"---\ncreated: {value}\n---\n\n# Keep\n")
    assert metadata["created"] == value
    assert body == "\n# Keep\n"
    assert isinstance(yaml.safe_load(f"created: {value}")["created"], datetime)
    assert frontmatter_timestamp(value) == value


def test_existing_date_is_preserved_on_overwrite(tmp_path: Path) -> None:
    from test_pipeline import FakeProvider, _config, _source

    from doc_summarizer.pipeline import summarize
    from doc_summarizer.validation import validate_summary

    source = _source(tmp_path)
    result = summarize(str(source), _config(tmp_path), provider=FakeProvider())
    metadata, _ = split_frontmatter(result.path.read_text(encoding="utf-8"))
    created = "2026-07-01T01:02:03.123456789Z"
    text = result.path.read_text(encoding="utf-8").replace(
        f'created: "{metadata["created"]}"', f"date: {created}"
    )
    result.path.write_text(text, encoding="utf-8")
    assert validate_summary(result.path) == []
    source.write_text(source.read_text(encoding="utf-8") + "\nExtra fact.", encoding="utf-8")
    updated = summarize(str(source), _config(tmp_path), provider=FakeProvider(), overwrite=True)
    after, _ = split_frontmatter(updated.path.read_text(encoding="utf-8"))
    assert "date" not in after
    assert after["created"] == created
    assert after["noteId"] == metadata["noteId"]
    assert f'created: "{created}"' in updated.path.read_text(encoding="utf-8")
    assert validate_summary(updated.path) == []


def test_new_note_validator_checks_quotes(tmp_path: Path) -> None:
    from test_pipeline import FakeProvider, _config, _source

    from doc_summarizer.pipeline import summarize
    from doc_summarizer.validation import validate_summary_text

    result = summarize(str(_source(tmp_path)), _config(tmp_path), provider=FakeProvider())
    text = result.path.read_text(encoding="utf-8")
    metadata, _ = split_frontmatter(text)
    unquoted = text.replace(f'updated: "{metadata["updated"]}"', f"updated: {metadata['updated']}")
    assert "dates must use double quotes and Windows paths single quotes" in validate_summary_text(
        unquoted
    )
