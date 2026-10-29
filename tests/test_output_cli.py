from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

import pytest

import doc_summarizer.cli as cli
import doc_summarizer.config as config
import doc_summarizer.prompting as prompting
from doc_summarizer.models import SummaryResult
from doc_summarizer.output import config_lines


@pytest.mark.parametrize("position", [0, 1, 2, 3])
def test_json_survives_nested_commands(position, capsys):
    args = ["config", "list", "--quiet"]
    args.insert(position, "--json")
    assert cli.main(args) == 0
    capture = capsys.readouterr()
    assert "values" in json.loads(capture.out) and capture.err == ""


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "command", ["summary", "series", "compare", "validate", "config", "prompt"]
)
def test_commands_use_same_result_in_both_formats(
    tmp_path, monkeypatch, capsys, json_mode, command
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "user_root", lambda: tmp_path / "user")
    monkeypatch.setattr(prompting, "user_prompts_root", lambda: tmp_path / "prompts")
    first, second = tmp_path / "日本語.md", tmp_path / "second.md"
    first.write_text("# First\n\nContent.", encoding="utf-8")
    second.write_text("# Second\n\nContent.", encoding="utf-8")
    args = {
        "summary": ["summarize", str(first), "--dry-run"],
        "series": ["summarize", str(first), str(second), "--dry-run"],
        "compare": ["summarize", str(first), str(second), "--mode", "compare", "--dry-run"],
        "validate": ["validate", str(first)],
        "config": ["config", "init"],
        "prompt": ["prompt", "init"],
    }[command]
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    code = cli.main([*args, *(["--json"] if json_mode else [])])
    assert code == (1 if command == "validate" else 0)
    capture = capsys.readouterr()
    if json_mode:
        result = json.loads(capture.out)
        assert "path" in result
    else:
        assert all("=" in line for line in capture.out.splitlines())
        assert "path=" in capture.out
    if command in ("summary", "series", "compare", "validate"):
        assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "argv,code",
    [
        ([], 2),
        (["unknown"], 2),
        (["summarize", "--max-input-bytes", "bad"], 2),
        (["config", "list", "--config", "absent.yaml"], 1),
        (["summarize", "--dry-run"], 1),
    ],
)
def test_errors_are_final_results(argv, code, json_mode, capsys):
    assert cli.main([*argv, *(["--json"] if json_mode else [])]) == code
    capture = capsys.readouterr()
    if json_mode:
        result = json.loads(capture.out)
        assert result["status"] == "failed" and result["counts"]["failed"] == 1
    else:
        assert "status=failed" in capture.out and "error=" in capture.out
    assert "\x1b" not in capture.out


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "exc,code", [(KeyboardInterrupt(), 130), (RuntimeError("failure"), 1), (OSError("denied"), 1)]
)
def test_runtime_and_interrupt_preserve_format(monkeypatch, capsys, json_mode, exc, code):
    def fail(*args, **kwargs):
        raise exc

    monkeypatch.setattr(cli, "validate_summary", fail)
    assert cli.main(["validate", "target.md", *(["--json"] if json_mode else [])]) == code
    output = capsys.readouterr().out
    if json_mode:
        assert json.loads(output)["targets"]["path"] == "target.md"
    else:
        assert "targets.path=target.md" in output


@pytest.mark.parametrize("status", ["created", "updated", "unchanged", "planned"])
@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("verbosity", [[], ["--quiet"], ["--verbose"]])
@pytest.mark.parametrize("tty", [False, True])
def test_status_verbosity_and_tty_do_not_change_output(
    monkeypatch, capsys, status, json_mode, verbosity, tty
):
    result = SummaryResult(path=Path("result.md"), source_path=Path("source.md"), status=status)
    monkeypatch.setattr(cli, "summarize", lambda *a, **kw: result)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: tty)
    assert cli.main([*verbosity, "summarize", "source.md", *(["--json"] if json_mode else [])]) == 0
    capture = capsys.readouterr()
    if json_mode:
        assert json.loads(capture.out)["status"] == status
    else:
        assert f"status={status}" in capture.out
    if "--quiet" in verbosity:
        assert capture.err == ""


def test_paths_and_control_characters_are_copyable():
    path = PureWindowsPath("C:/Users/ExampleUser/日本語/" + "long" * 100 + ".md")
    assert config_lines({"path": path}) == [f"path={path}"]
    assert config_lines({"line\nkey": "a\r\n\t\x1b"}) == [r"line\u000akey=a\r\n\t\u001b"]


def test_help_and_version_remain_normal(capsys):
    for option in ("--help", "--version"):
        with pytest.raises(SystemExit) as result:
            cli.main(["--json", option])
        assert result.value.code == 0
        assert "tkn-doc-summarizer" in capsys.readouterr().out
