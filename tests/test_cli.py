from __future__ import annotations

import json
from pathlib import Path

import pytest

import doc_summarizer.config as config_module
from doc_summarizer.cli import build_parser, config_lines, main


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


def test_compare_dry_run_reports_compare_profile(tmp_path: Path, capsys: object) -> None:
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    first.write_text("# One\n\nShared idea.", encoding="utf-8")
    second.write_text("# Two\n\nDifferent view.", encoding="utf-8")

    code = main(
        [
            "synthesize",
            str(first),
            str(second),
            "--mode",
            "compare",
            "--title",
            "Article comparison",
            "--output-root",
            str(tmp_path / "output"),
            "--dry-run",
        ]
    )

    assert code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload["details"]["synthesis_mode"] == "compare"
    assert payload["details"]["summary_profile"] == "compare-ja"
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


def test_config_list_json_reports_summary_profile_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-config.yaml",
    )

    assert main(["config", "list", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    profile = payload["values"]["summary_profile"]
    assert profile["name"] == "default-ja"
    assert profile["source"].endswith("summary_profiles/default-ja")
    assert profile["output_schema"]["source"].endswith("output.schema.json")
    assert profile["template"]["source"].endswith("template.md")
    comparison = payload["values"]["comparison_profile"]
    assert comparison["name"] == "compare-ja"
    assert comparison["source"].endswith("comparison_profiles/default-ja")
    assert payload["values"]["source_path_format"] == "native"
    assert payload["value_sources"]["source_path_format"] == "built-in defaults"


def test_config_init_reports_created_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
) -> None:
    target = tmp_path / "user" / "config.yaml"
    monkeypatch.setattr(config_module, "global_config_path", lambda: target)

    assert main(["config", "init"]) == 0

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.out)
    assert payload == {
        "status": "created",
        "path": str(target),
        "backup_path": None,
    }
    assert "[SUCCESS]" in captured.err


def test_config_init_refuses_to_replace_edited_file_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("model: custom\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "global_config_path", lambda: target)

    assert main(["config", "init"]) == 1

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert "re-run with --force" in captured.err
    assert target.read_text(encoding="utf-8") == "model: custom\n"


def test_config_list_json_accepts_cli_summary_profile_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: object,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-config.yaml",
    )

    assert main(["config", "list", "--json", "--summary-profile", "default-en"]) == 0

    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert payload["values"]["summary_profile"]["name"] == "default-en"
    assert payload["value_sources"]["summary_profile"] == "CLI options"


@pytest.mark.parametrize("json_output", [False, True])
def test_config_list_is_read_only_and_reports_winning_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    json_output: bool,
) -> None:
    import subprocess

    import doc_summarizer.providers.bridge as bridge_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "user_root", lambda: tmp_path / "user")
    global_config = tmp_path / "global.yaml"
    global_config.write_text("max_input_bytes: 100\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "global_config_path", lambda: global_config)
    local_config = tmp_path / ".tkn" / "config.yaml"
    local_config.parent.mkdir()
    local_config.write_text("max_input_bytes: 200\n", encoding="utf-8")
    explicit_config = tmp_path / "explicit.yaml"
    explicit_config.write_text("max_input_bytes: 300\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    def unexpected_execution(*args: object, **kwargs: object) -> None:
        raise AssertionError("Configuration listing must not execute a provider or subprocess")

    monkeypatch.setattr(bridge_module.Runtime, "generate", unexpected_execution)
    monkeypatch.setattr(subprocess, "Popen", unexpected_execution)
    args = [
        "config",
        "list",
        "--config",
        str(explicit_config),
        "--max-input-bytes",
        "400",
        "--summary-profile",
        "default-en",
    ]
    if json_output:
        args.append("--json")
    assert main(args) == 0
    captured = capsys.readouterr()
    assert captured.err == "[INFO] Showing resolved configuration\n"
    assert "\x1b" not in captured.out
    if json_output:
        payload = json.loads(captured.out)
        assert payload["sources"] == [
            "built-in defaults",
            str(global_config),
            str(local_config),
            str(explicit_config),
            "CLI options",
        ]
        assert payload["values"]["max_input_bytes"] == 400
        assert payload["value_sources"]["max_input_bytes"] == "CLI options"
        assert payload["generationResolved"]["will_call_provider"] is False
    else:
        lines = captured.out.splitlines()
        assert all("=" in line for line in lines)
        assert f"sources[3]={explicit_config}" in lines
        assert "values.max_input_bytes=400" in lines
        assert "value_sources.max_input_bytes=CLI options" in lines
        assert "values.summary_profile.name=default-en" in lines
        assert "values.source_roots=[]" in lines
        assert "values.generation.profiles.codex.overrides={}" in lines
        assert "generationResolved.will_call_provider=false" in lines
    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before
    assert not (tmp_path / "user").exists()


def test_config_lines_preserve_paths_and_single_line_values() -> None:
    assert config_lines(
        {
            "path": r"C:\Users\ExampleUser\Documents",
            "nested": {"items": [{"active": True}, False, None, 42, 1.5]},
            "empty_list": [],
            "empty_mapping": {},
            "text": "日本語=値\r\n\t\x1b",
        }
    ) == [
        r"path=C:\Users\ExampleUser\Documents",
        "nested.items[0].active=true",
        "nested.items[1]=false",
        "nested.items[2]=null",
        "nested.items[3]=42",
        "nested.items[4]=1.5",
        "empty_list=[]",
        "empty_mapping={}",
        r"text=日本語=値\r\n\t\u001b",
    ]


@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_config_list_quiet_suppresses_only_logs(
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
) -> None:
    assert main(["config", "list", "--quiet", *extra]) == 0
    captured = capsys.readouterr()
    assert captured.out and captured.err == ""


def test_config_list_help_and_removed_show(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as help_exit:
        parser.parse_args(["config", "list", "--help"])
    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    assert "--json" in help_text and "key=value" in help_text
    with pytest.raises(SystemExit) as old_exit:
        parser.parse_args(["config", "show"])
    assert old_exit.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_config_list_missing_explicit_config_returns_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
) -> None:
    assert main(["config", "list", "--config", str(tmp_path / "absent.yaml"), *extra]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ERROR]" in captured.err and "does not exist" in captured.err
