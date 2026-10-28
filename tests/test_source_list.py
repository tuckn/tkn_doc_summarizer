from __future__ import annotations

from pathlib import Path

import pytest

from doc_summarizer.source_list import read_source_list


def test_utf8_bom_list_preserves_order_urls_and_relative_paths(tmp_path: Path) -> None:
    folder = tmp_path / "lists"
    folder.mkdir()
    listing = folder / "sources.txt"
    absolute = tmp_path / "absolute.md"
    listing.write_text(
        f"# A comment\n\n../日本語 with spaces.md\nhttps://example.com/a#part\n{absolute}\n",
        encoding="utf-8-sig",
    )
    assert read_source_list(listing) == [
        str((folder / "../日本語 with spaces.md").absolute()),
        "https://example.com/a#part",
        str(absolute),
    ]


@pytest.mark.parametrize("content", [b"# empty\n", b"\xff", b'"quoted.md"\n', b"bad\x00.md"])
def test_invalid_lists_are_rejected(tmp_path: Path, content: bytes) -> None:
    listing = tmp_path / "sources.txt"
    listing.write_bytes(content)
    with pytest.raises(ValueError):
        read_source_list(listing)


def test_source_list_has_a_bounded_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("doc_summarizer.source_list.MAX_SOURCE_LIST_BYTES", 8)
    listing = tmp_path / "sources.txt"
    listing.write_bytes(b"a.md\nb.md\n")
    with pytest.raises(ValueError, match="exceeds"):
        read_source_list(listing)
