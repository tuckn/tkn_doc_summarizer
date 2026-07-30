from __future__ import annotations

import json
from pathlib import Path

from doc_summarizer.cli import build_parser, main


def test_help_names_url_behavior(capsys: object) -> None:
    parser = build_parser()
    assert "does not fetch web pages" in parser.description


def test_dry_run_outputs_only_json_to_stdout(
    tmp_path: Path,
    capsys: object,
) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Title\n\nContent.", encoding="utf-8")
    code = main(
        [
            "summarize",
            str(source),
            "--output-root",
            str(tmp_path / "output"),
            "--dry-run",
        ]
    )
    assert code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["status"] == "planned"
    assert "[INFO]" in captured.err
    assert not (tmp_path / "output").exists()


def test_validate_invalid_note_returns_nonzero(
    tmp_path: Path,
    capsys: object,
) -> None:
    path = tmp_path / "invalid.md"
    path.write_text("# Not generated", encoding="utf-8")
    assert main(["validate", str(path)]) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out)["valid"] is False
    assert "[ERROR]" in captured.err


def test_quiet_and_verbose_are_mutually_exclusive() -> None:
    parser = build_parser()
    try:
        parser.parse_args(["summarize", "a.md", "--quiet", "--verbose"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("mutually exclusive arguments were accepted")
