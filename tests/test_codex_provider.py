from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from doc_summarizer.models import DocumentSource, SummaryRequest
from doc_summarizer.prompting import PROMPT_ENVELOPE_VERSION
from doc_summarizer.providers.codex import CodexProvider


def _request(tmp_path: Path) -> SummaryRequest:
    path = tmp_path / "source.md"
    path.write_text("content", encoding="utf-8")
    return SummaryRequest(
        source=DocumentSource(
            path=path,
            title="Title",
            content="content",
            source_sha256="0" * 64,
        ),
        prompt_envelope_version=PROMPT_ENVELOPE_VERSION,
    )


def _document_json() -> str:
    return json.dumps(
        {
            "description": "Description",
            "summary": "Summary",
            "structuring": [{"heading": "Topic", "details": ["Detail"]}],
            "key_points": ["Point"],
            "technical_terms": ["**Term**: Explanation."],
            "conclusion": "Conclusion",
        }
    )


def test_codex_provider_uses_structured_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "codex-cli 1.0\n", "")
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(_document_json(), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "model: test-model\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CodexProvider(timeout_seconds=60).generate(_request(tmp_path))
    assert result.model == "test-model"
    assert "--output-schema" in commands[1]
    assert result.document.summary == "Summary"


def test_codex_timeout_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(command, 0, "codex-cli 1.0\n", "")
        raise subprocess.TimeoutExpired(command, timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="timed out"):
        CodexProvider(timeout_seconds=1).generate(_request(tmp_path))
