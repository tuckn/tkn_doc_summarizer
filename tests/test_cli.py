from __future__ import annotations

import json
from pathlib import Path

import pytest

import doc_summarizer.config as config_module
from doc_summarizer.cli import build_parser, main


def test_help_names_url_behavior(capsys: object) -> None:
    parser = build_parser()
    assert parser.prog == "tkn-doc-summarizer"
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


def test_series_dry_run_outputs_resolved_sources_without_writes(
    tmp_path: Path,
    capsys: object,
) -> None:
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    first.write_text("# One\n\nFirst.", encoding="utf-8")
    second.write_text("# Two\n\nSecond.", encoding="utf-8")

    code = main(
        [
            "synthesize",
            str(first),
            str(second),
            "--title",
            "Complete article",
            "--output-root",
            str(tmp_path / "output"),
            "--dry-run",
        ]
    )

    assert code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["status"] == "planned"
    assert payload["details"]["synthesis_mode"] == "series"
    assert payload["details"]["source_count"] == 2
    assert not (tmp_path / "output").exists()


def test_series_requires_two_cli_sources(tmp_path: Path, capsys: object) -> None:
    source = tmp_path / "one.md"
    source.write_text("# One\n\nFirst.", encoding="utf-8")

    code = main(["synthesize", str(source), "--dry-run"])

    assert code == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "at least two sources" in captured.err


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


def test_config_show_reports_summary_profile_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-config.yaml",
    )

    assert main(["config", "show"]) == 0

    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    profile = payload["values"]["summary_profile"]
    assert profile["name"] == "default-ja"
    assert profile["source"].endswith("summary_profiles/default-ja")
    assert profile["output_schema"]["source"].endswith("output.schema.json")
    assert profile["template"]["source"].endswith("template.md")


def test_config_show_accepts_cli_summary_profile_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-config.yaml",
    )

    assert main(["config", "show", "--summary-profile", "default-en"]) == 0

    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert payload["values"]["summary_profile"]["name"] == "default-en"
    assert payload["value_sources"]["summary_profile"] == "CLI options"
