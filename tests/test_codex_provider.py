from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from doc_summarizer.models import ComparisonRequest, DocumentSource, SummaryRequest
from doc_summarizer.prompting import COMPARISON_PROMPT_ENVELOPE_VERSION, PROMPT_ENVELOPE_VERSION
from doc_summarizer.providers.codex import CodexProvider
from doc_summarizer.providers.comparison import CodexComparisonProvider
from doc_summarizer.synthesis import resolve_synthesis_sources


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
            "title": "Generated title",
            "description": "Description",
            "summary": "Summary",
            "structuring": [
                {
                    "heading": "Topic",
                    "details": [],
                    "subsections": [{"heading": "Subtopic", "details": ["Detail"]}],
                }
            ],
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
        schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
        assert "title" in schema["required"]
        assert "SummarySubsection" in schema["$defs"]
        assert "English paragraph" in schema["properties"]["summary"]["description"]
        assert "source-faithful English summary" in str(kwargs["input"])
        summary_section = schema["$defs"]["SummarySection"]
        assert set(summary_section["required"]) == set(summary_section["properties"])
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(_document_json(), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "model: test-model\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CodexProvider(
        timeout_seconds=60,
        summary_profile="default-en",
    ).generate(_request(tmp_path))
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


def test_codex_comparison_provider_uses_comparison_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n\nShared idea.", encoding="utf-8")
    second.write_text("# Second\n\nDifferent view.", encoding="utf-8")
    source_set = resolve_synthesis_sources(
        [str(first), str(second)],
        mode="compare",
        title="Comparison",
        source_roots=[],
        max_input_bytes=1_000,
        max_total_input_bytes=2_000,
    )
    request = ComparisonRequest(
        source_set=source_set,
        prompt_envelope_version=COMPARISON_PROMPT_ENVELOPE_VERSION,
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "codex-cli 1.0\n", "")
        schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
        assert "title" in schema["required"]
        assert schema["$defs"]["CommonConcept"]["properties"]["source_ids"]["minItems"] == 2
        assert "independent sources" in str(kwargs["input"])
        output = {
            "title": "Generated comparison title",
            "description": "Description",
            "summary": "Summary",
            "common_concepts": [{"text": "Shared", "source_ids": ["S1", "S2"]}],
            "perspectives": [
                {"heading": "Views", "explanation": "Different", "source_ids": ["S1", "S2"]}
            ],
            "disagreements": [],
            "source_specific_insights": [],
            "technical_terms": ["**Term**: Explanation."],
            "conclusion": "Conclusion",
        }
        Path(command[command.index("--output-last-message") + 1]).write_text(
            json.dumps(output), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "model: compare-model\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CodexComparisonProvider(summary_profile="default-en").generate(request)
    assert result.model == "compare-model"
    assert result.document.common_concepts[0].source_ids == ["S1", "S2"]
