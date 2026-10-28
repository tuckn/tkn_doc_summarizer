from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from tkn_genai_bridge import GenerationRequest, Profile, Runtime
from tkn_genai_bridge.providers.base import ProviderResponse

import doc_summarizer.providers.bridge as bridge_module
from doc_summarizer.cli import main
from doc_summarizer.config import AppConfig
from doc_summarizer.models import MeetingMinutesDocument
from doc_summarizer.pipeline import summarize, synthesize_compare, synthesize_series
from doc_summarizer.prompting import initialize_user_prompt
from doc_summarizer.providers.bridge import BridgeProvider
from doc_summarizer.source import split_frontmatter
from doc_summarizer.summary_resources import load_summary_profile
from doc_summarizer.validation import validate_summary, validate_summary_text


def _point(source_id: str = "S1") -> dict[str, Any]:
    return {
        "text": "説明者（個人要確認）が開始日を条件付きの案として説明した。",
        "basis": "statement",
        "certainty": "provisional",
        "source_ids": [source_id],
    }


class MeetingBackend:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []
        self.data: dict[str, Any] = {
            "title": "開始方針の確認",
            "summary": [_point()],
            "facts": [{"heading": "開始の前提", "items": [_point()]}],
            "open_questions": [_point()],
            "raid": [
                {
                    **_point(), "category": category,
                    "owner": "会社A（個人要確認）",
                    "deadline": "未指定（要確認）", "status": "調整待ち",
                }
                for category in ("Risk", "Action", "Issue", "Decision")
            ],
            "next_checks": [_point()],
            "limitations": ["話者の実名・日程の確定は確認できていない。"],
        }

    def generate(self, profile: Profile, request: GenerationRequest) -> ProviderResponse:
        assert request.schema_name == "meeting_minutes"
        assert request.images == []
        self.requests.append(request)
        return ProviderResponse(data=deepcopy(self.data), response_model="test-model")


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> MeetingBackend:
    backend = MeetingBackend()
    monkeypatch.setattr(bridge_module, "Runtime", lambda p: Runtime(p, backend=backend))
    return backend


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        output_root=tmp_path / "out", reports_root=tmp_path / "reports",
        generation={"summary": {"profiles": {"default": {
            "summary_profile": "meeting-minutes-ja",
        }}}},
    )


def _sources(tmp_path: Path) -> list[str]:
    paths = [tmp_path / "recording-1.md", tmp_path / "recording-2.md"]
    for path in paths:
        path.write_text(
            "# 会議\n\n[00:00:01 - 00:00:05] [Speaker 1] 開始日は未承認です。\n",
            encoding="utf-8",
        )
    return list(map(str, paths))


def test_meeting_resources_match_dedicated_contract() -> None:
    profile = load_summary_profile("meeting-minutes-ja")
    assert profile.schema.value == MeetingMinutesDocument.model_json_schema()
    assert profile.template.technical_terms_heading is None
    assert len(profile.template.required_headings) == 5
    assert "エグゼクティブ" in profile.prompt.instructions
    assert "金額・人数・期限" in profile.prompt.instructions
    assert "source_ids" in profile.prompt.instructions
    assert "conclusion" not in profile.schema.value["properties"]


@pytest.mark.parametrize("mode", ["single", "series"])
def test_generate_meeting_minutes_and_reuse_with_context(
    tmp_path: Path, backend: MeetingBackend, mode: str
) -> None:
    sources = _sources(tmp_path)
    config = _config(tmp_path)
    if mode == "series":
        backend.data["facts"][0]["items"].append(_point("S2"))
    backend.data["summary"].append({
        **_point(), "text": "今回の目的は質問による認識合わせ。",
        "basis": "context", "source_ids": [],
    })
    run = summarize if mode == "single" else synthesize_series
    source = sources[0] if mode == "single" else sources
    planned = run(
        source, config, context="質問による認識合わせ。",
        conversation_date="2026-10-15", dry_run=True,
    )
    assert planned.status == "planned"
    assert planned.path.name.startswith("20261015_")
    assert not backend.requests and not config.output_root.exists()
    assert not config.reports_root.exists()
    result = run(
        source, config, context="質問による認識合わせ。", conversation_date="2026-10-15"
    )
    metadata, body = split_frontmatter(result.path.read_text(encoding="utf-8"))
    assert metadata["schemaVersion"] == ("12.0" if mode == "single" else "13.0")
    assert metadata["summaryProfile"] == "meeting-minutes-ja"
    assert metadata["conversationDate"] == "2026-10-15"
    assert metadata["contextSha256"] == result.details["context_sha256"]
    assert body.index("## 1. 概要") < body.index("## 2. 会話で確認できた事実")
    assert "【ユーザー補足・暫定】" in body
    assert "【発言・暫定】" in body
    for category in ("Risk", "Action", "Issue", "Decision"):
        assert f"| {category[0]}1 | {category} |" in body
    assert "| 会社A（個人要確認） | 未指定（要確認） | 調整待ち |" in body
    assert "専門用語" not in body and "## 2. 結論" not in body
    assert "consecutive article pages" in backend.requests[0].prompt
    assert "CONVERSATION_DATE: 2026-10-15" in backend.requests[0].prompt
    assert not validate_summary(result.path)
    assert run(
        source, config, context="質問による認識合わせ。", conversation_date="2026-10-15"
    ).status == "unchanged"
    assert len(backend.requests) == 1
    with pytest.raises(RuntimeError, match="--overwrite"):
        run(source, config, context="別の背景。", conversation_date="2026-10-15")


def test_unknown_date_and_empty_sections_do_not_invent_content(
    tmp_path: Path, backend: MeetingBackend
) -> None:
    backend.data.update(facts=[], open_questions=[], raid=[], next_checks=[])
    result = summarize(_sources(tmp_path)[0], _config(tmp_path))
    metadata, body = split_frontmatter(result.path.read_text(encoding="utf-8"))
    assert metadata["conversationDate"] is None
    assert "会話日: 未確認" in body
    assert "RAID に該当する項目は抽出されていません。" in body
    assert not validate_summary(result.path)


@pytest.mark.parametrize("change", ["unknown_id", "context_fact", "no_context", "no_owner"])
def test_invalid_minutes_never_create_a_note_or_leak_response(
    tmp_path: Path, backend: MeetingBackend, change: str
) -> None:
    if change == "unknown_id":
        backend.data["summary"][0]["source_ids"] = ["PRIVATE_RESPONSE"]
    elif change == "context_fact":
        backend.data["facts"][0]["items"][0].update(basis="context", source_ids=[])
    elif change == "no_context":
        backend.data["summary"][0].update(basis="context", source_ids=[])
    else:
        backend.data["raid"][0]["owner"] = ""
    config = _config(tmp_path)
    with pytest.raises(RuntimeError) as error:
        summarize(
            _sources(tmp_path)[0], config,
            context="背景" if change == "context_fact" else None,
        )
    assert "PRIVATE_RESPONSE" not in str(error.value)
    assert not config.output_root.exists()
    report = next(config.reports_root.glob("*.json")).read_text(encoding="utf-8")
    assert "PRIVATE_RESPONSE" not in report


def test_markdown_table_cells_and_persisted_contract(
    tmp_path: Path, backend: MeetingBackend
) -> None:
    backend.data["raid"][0]["owner"] = "会社A | 会社B\n要確認"
    result = summarize(_sources(tmp_path)[0], _config(tmp_path), context="背景")
    text = result.path.read_text(encoding="utf-8")
    assert "会社A &#124; 会社B 要確認" in text
    assert not validate_summary(result.path)
    assert validate_summary_text(text.replace("[S1](", "[S9]("), verify_source=False)
    assert validate_summary_text(text.replace("オーナー | 期限", "担当 | 日時"))
    assert validate_summary_text(text.replace("contextSha256:", "badContextSha256:"))


def test_meeting_profile_config_and_custom_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import doc_summarizer.prompting as prompting

    assert main(["config", "list", "--summary-profile", "meeting-minutes-ja", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["values"]["summary_profile"]["name"] == (
        "meeting-minutes-ja"
    )
    monkeypatch.setattr(prompting, "user_prompts_root", lambda: tmp_path / "prompts")
    path = initialize_user_prompt("meeting.md", profile_name="meeting-minutes-ja")
    provider = BridgeProvider(summary_profile="meeting-minutes-ja", summary_prompt=path)
    assert provider.profile.schema.value == MeetingMinutesDocument.model_json_schema()
    assert provider.prompt.mode == "custom"
    comparison = synthesize_compare(_sources(tmp_path), _config(tmp_path), dry_run=True)
    assert comparison.details["summary_profile"] == "compare-ja"
