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
from doc_summarizer.conversation import evidence_errors, validate_conversation_document
from doc_summarizer.models import ConversationDocument, ConversationEvidence
from doc_summarizer.pipeline import summarize, synthesize_compare, synthesize_series
from doc_summarizer.providers.bridge import BridgeProvider
from doc_summarizer.source import resolve_source, split_frontmatter
from doc_summarizer.summary_resources import load_summary_profile
from doc_summarizer.validation import validate_summary, validate_summary_text


def _item(source_id: str) -> dict[str, Any]:
    return {
        "text": "子どもがあるキャラクターのグッズを欲しがる、と語られた。",
        "kind": "statement",
        "subject": "発言者の子ども（親の実名は未確認）",
        "speaker_name": None,
        "identity_status": "unknown",
        "identity_basis": "実名との対応未確認",
        "uncertainty": "発言の事実性と家族の実名は未確認",
        "evidence": [
            {
                "source_id": source_id,
                "start": "00:00:01",
                "end": "00:00:05",
                "speaker_label": "Speaker 1",
            }
        ],
    }


def _data(count: int = 4) -> dict[str, Any]:
    return {
        "title": "近況と好みについての会話記録",
        "summary": "家族の近況や好みが話題になった。",
        "topics": [
            {"heading": "家族の好み", "items": [_item(f"S{i}") for i in range(1, count + 1)]}
        ],
        "plans": [],
        "unconfirmed": [],
        "limitations": ["話者分離や固有名詞に誤認識の可能性がある。"],
    }


class ConversationBackend:
    def __init__(self, count: int = 4) -> None:
        self.requests: list[GenerationRequest] = []
        self.data = _data(count)

    def generate(self, profile: Profile, request: GenerationRequest) -> ProviderResponse:
        assert request.schema_name == "conversation_record"
        assert request.images == []
        self.requests.append(request)
        return ProviderResponse(data=deepcopy(self.data), response_model="test-model")


@pytest.fixture
def sources(tmp_path: Path) -> list[str]:
    result: list[str] = []
    for i in range(1, 5):
        path = tmp_path / f"recording-{i}.md"
        path.write_text(
            '---\ncreated: "2026-10-21T12:00:00+09:00"\n---\n\n'
            f"# Recording {i}\n\n"
            "[00:00:01 - 00:00:05] [Speaker 1] 子どもがグッズを欲しがっている。\n"
            "[00:00:05 - 00:00:07] [Speaker 2] いつか買いに行きたいね。\n",
            encoding="utf-8",
        )
        result.append(str(path))
    return result


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        output_root=tmp_path / "out",
        reports_root=tmp_path / "reports",
        generation={"summary": {"profiles": {"default": {"summary_profile": "conversation-ja"}}}},
    )


def _backend(monkeypatch: pytest.MonkeyPatch, count: int = 4) -> ConversationBackend:
    backend = ConversationBackend(count)
    monkeypatch.setattr(bridge_module, "Runtime", lambda profile: Runtime(profile, backend=backend))
    return backend


def test_conversation_resources_match_dedicated_contract() -> None:
    profile = load_summary_profile("conversation-ja")
    assert profile.schema.value == ConversationDocument.model_json_schema()
    assert profile.template.technical_terms_heading is None
    assert len(profile.template.required_headings) == 5
    assert "conclusion" not in profile.schema.value["properties"]
    assert "technical_terms" not in profile.schema.value["properties"]
    assert "別ファイルの同じラベルを同一人物とみなさない" in profile.prompt.instructions


def test_four_recordings_generate_one_grounded_record_and_reuse(
    tmp_path: Path,
    sources: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend(monkeypatch)
    config = _config(tmp_path)
    planned = synthesize_series(sources, config, conversation_date="2026-10-17", dry_run=True)
    assert planned.details["source_count"] == 4
    assert planned.details["bridge_plan"]["will_call_provider"] is False
    assert planned.path.name.startswith("20261017_")
    assert not config.output_root.exists() and not config.reports_root.exists()
    assert backend.requests == []
    result = synthesize_series(sources, config, conversation_date="2026-10-17")
    assert len(backend.requests) == 1
    prompt = backend.requests[0].prompt
    assert "consecutive pages" not in prompt
    assert "CONVERSATION_DATE: 2026-10-17" in prompt
    assert prompt.index("BEGIN_DOCUMENT ID=S1") < prompt.index("BEGIN_DOCUMENT ID=S4")
    text = result.path.read_text(encoding="utf-8")
    metadata, body = split_frontmatter(text)
    assert metadata["schemaVersion"] == "11.0"
    assert metadata["conversationDate"] == "2026-10-17"
    assert metadata["sourceSetPublished"].startswith("2026-10-21")
    assert metadata["created"] != metadata["conversationDate"]
    assert len(metadata["sources"]) == 4
    for i in range(1, 5):
        assert f"[S{i} 00:00:01–00:00:05 / Speaker 1]" in body
    assert "不明・未確認" in body
    assert "## 2. 結論" not in body and "専門用語" not in body
    assert not validate_summary(result.path)
    second = synthesize_series(sources, config, conversation_date="2026-10-17")
    assert second.status == "unchanged" and len(backend.requests) == 1
    with pytest.raises(RuntimeError, match="--overwrite"):
        synthesize_series(sources, config, conversation_date="2026-10-18")
    updated = synthesize_series(
        sources,
        config,
        conversation_date="2026-10-18",
        overwrite=True,
    )
    changed, _ = split_frontmatter(updated.path.read_text(encoding="utf-8"))
    assert changed["conversationDate"] == "2026-10-18"
    assert changed["noteId"] == metadata["noteId"]
    assert changed["created"] == metadata["created"]


def test_single_recording_leaves_date_unknown(
    tmp_path: Path,
    sources: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _backend(monkeypatch, 1)
    result = summarize(sources[0], _config(tmp_path))
    metadata, body = split_frontmatter(result.path.read_text(encoding="utf-8"))
    assert metadata["schemaVersion"] == "10.0"
    assert metadata["conversationDate"] is None
    assert "会話日: 未確認" in body
    assert not validate_summary(result.path)


def test_conversation_profile_receives_context(
    tmp_path: Path, sources: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _backend(monkeypatch, 1)
    result = summarize(sources[0], _config(tmp_path), context="Background about the conversation.")
    assert "Background about the conversation." in backend.requests[0].prompt
    assert "SUPPLEMENTARY_CONTEXT_JSON:" in backend.requests[0].prompt
    assert not validate_summary(result.path)
    assert summarize(
        sources[0], _config(tmp_path), context="Background about the conversation."
    ).status == "unchanged"


@pytest.mark.parametrize(
    "change", ["unknown_id", "time", "label", "missing_source", "identity", "plan"]
)
def test_invalid_provider_evidence_never_creates_record(
    tmp_path: Path,
    sources: list[str],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    backend = _backend(monkeypatch)
    item = backend.data["topics"][0]["items"][0]
    if change == "unknown_id":
        item["evidence"][0]["source_id"] = "S9"
    elif change == "time":
        item["evidence"][0]["start"] = "00:00:02"
    elif change == "label":
        item["evidence"][0]["speaker_label"] = "PRIVATE_RESPONSE"
    elif change == "missing_source":
        backend.data["topics"][0]["items"].pop()
    elif change == "identity":
        item["speaker_name"] = "PRIVATE_RESPONSE"
    else:
        backend.data["plans"] = [deepcopy(item)]
    config = _config(tmp_path)
    with pytest.raises(RuntimeError) as error:
        synthesize_series(sources, config)
    assert "PRIVATE_RESPONSE" not in str(error.value)
    assert not config.output_root.exists()
    report = next(config.reports_root.glob("*.json")).read_text(encoding="utf-8")
    assert "PRIVATE_RESPONSE" not in report


def test_persisted_citations_are_validated_even_without_glossary(
    tmp_path: Path,
    sources: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _backend(monkeypatch)
    result = synthesize_series(sources, _config(tmp_path))
    text = result.path.read_text(encoding="utf-8")
    assert any(
        "boundaries" in e for e in validate_summary_text(text.replace("00:00:01–", "00:00:02–"))
    )
    assert any(
        "speaker label" in e
        for e in validate_summary_text(text.replace("/ Speaker 1]", "/ Speaker 9]"))
    )
    assert validate_summary_text(text.replace("S4 00:00:01", "S9 00:00:01"), verify_source=False)
    assert validate_summary_text(text.replace("（種別:", "（分類:"), verify_source=False)


def test_wishes_remain_wishes_and_source_labels_are_not_people(sources: list[str]) -> None:
    data = _data()
    wish = _item("S1")
    wish.update(kind="wish", text="いつか買い物に行きたいと語られた。")
    wish["evidence"] = [
        {
            "source_id": "S1",
            "start": "00:00:05",
            "end": "00:00:07",
            "speaker_label": "Speaker 2",
        }
    ]
    data["plans"] = [wish]
    document = ConversationDocument.model_validate(data)
    documents = {
        f"S{i}": resolve_source(path, source_roots=[], max_input_bytes=10000)
        for i, path in enumerate(sources, 1)
    }
    assert not validate_conversation_document(document, sources=documents)
    assert document.plans[0].kind == "wish"
    assert all(item.speaker_name is None for item in document.topics[0].items)


@pytest.mark.parametrize("start,end", [(None, None), ("00:00:01", None), ("00:00:07", "00:00:01")])
def test_timestamped_input_rejects_missing_or_reversed_ranges(
    start: str | None, end: str | None
) -> None:
    evidence = ConversationEvidence(source_id="S1", start=start, end=end, speaker_label="Speaker 1")
    assert evidence_errors(evidence, "[00:00:01 - 00:00:05] [Speaker 1] 発言")


def test_untimed_input_does_not_invent_timestamps() -> None:
    evidence = ConversationEvidence(source_id="S1", start=None, end=None, speaker_label=None)
    assert not evidence_errors(evidence, "時刻も話者ラベルもない発言。")
    fabricated = evidence.model_copy(update={"start": "00:00:01", "end": "00:00:05"})
    assert evidence_errors(fabricated, "時刻も話者ラベルもない発言。")


def test_label_elsewhere_in_source_does_not_support_cited_range() -> None:
    evidence = ConversationEvidence(
        source_id="S1",
        start="00:00:01",
        end="00:00:05",
        speaker_label="Speaker 2",
    )
    assert evidence_errors(
        evidence,
        "[00:00:01 - 00:00:05] [Speaker 1] 発言\n[00:00:06 - 00:00:07] [Speaker 2] 別の発言\n",
    )


def test_invalid_regeneration_keeps_existing_record(
    tmp_path: Path,
    sources: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend(monkeypatch)
    config = _config(tmp_path)
    result = synthesize_series(sources, config)
    before = result.path.read_bytes()
    backend.data["topics"][0]["items"][0]["evidence"][0]["start"] = "00:00:02"
    with pytest.raises(RuntimeError):
        synthesize_series(sources, config, overwrite=True)
    assert result.path.read_bytes() == before


@pytest.mark.parametrize("single", [True, False])
def test_article_profile_rejects_conversation_date_without_writes(
    tmp_path: Path,
    sources: list[str],
    single: bool,
) -> None:
    config = AppConfig(output_root=tmp_path / "out", reports_root=tmp_path / "reports")
    with pytest.raises(ValueError, match="conversation-ja"):
        if single:
            summarize(sources[0], config, conversation_date="2026-10-17", dry_run=True)
        else:
            synthesize_series(sources, config, conversation_date="2026-10-17", dry_run=True)
    assert not config.output_root.exists() and not config.reports_root.exists()


@pytest.mark.parametrize("value", ["2026-02-30", "20261017", "2026-1-7"])
def test_invalid_date_is_read_only(tmp_path: Path, sources: list[str], value: str) -> None:
    config = _config(tmp_path)
    with pytest.raises(ValueError, match="date"):
        synthesize_series(sources, config, conversation_date=value, dry_run=True)
    assert not config.output_root.exists() and not config.reports_root.exists()


def test_compare_is_independent_of_conversation_profile(tmp_path: Path, sources: list[str]) -> None:
    result = synthesize_compare(sources, _config(tmp_path), dry_run=True)
    assert result.details["summary_profile"] == "compare-ja"


def test_cli_config_supports_conversation_profile(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config", "list", "--summary-profile", "conversation-ja", "--json"]) == 0
    values = json.loads(capsys.readouterr().out)["values"]
    assert values["summary_profile"]["name"] == "conversation-ja"


def test_custom_prompt_keeps_conversation_schema(tmp_path: Path) -> None:
    path = tmp_path / "prompt.md"
    path.write_text(
        '---\ntype: prompt\nid: c457d8c6-d77d-41ac-aa6f-f61553764929\nversion: "1.0"\n---\n'
        "簡潔な会話記録にする。",
        encoding="utf-8",
    )
    provider = BridgeProvider(summary_profile="conversation-ja", summary_prompt=path)
    assert provider.prompt.mode == "custom"
    assert provider.profile.schema.value == ConversationDocument.model_json_schema()
