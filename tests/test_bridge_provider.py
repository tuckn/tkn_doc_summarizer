from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tkn_genai_bridge import GenerationRequest, Profile, ProviderError, Runtime
from tkn_genai_bridge.providers.base import ProviderResponse

import doc_summarizer.providers.bridge as bridge_module
from doc_summarizer.config import AppConfig
from doc_summarizer.models import ComparisonRequest, DocumentSource, SummaryRequest
from doc_summarizer.pipeline import summarize, synthesize_compare, synthesize_series
from doc_summarizer.prompting import COMPARISON_PROMPT_ENVELOPE_VERSION, PROMPT_ENVELOPE_VERSION
from doc_summarizer.providers import (
    BridgeComparisonProvider,
    BridgeProvider,
    ProviderExecutionError,
)
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


class FakeBackend:
    def __init__(self, *, error: bool = False, invalid: bool = False) -> None:
        self.requests: list[GenerationRequest] = []
        self.error = error
        self.invalid = invalid

    def generate(self, profile: Profile, request: GenerationRequest) -> ProviderResponse:
        assert request.images == [], "document generation must remain text-only"
        self.requests.append(request)
        if self.error:
            raise ProviderError("Generation timed out", code="timeout", submission_unknown=True)
        data = json.loads(_document_json())
        if request.schema_name == "document_comparison":
            data = {
                "title": "Comparison",
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
            if self.invalid:
                data["common_concepts"][0]["source_ids"] = ["S1", "PRIVATE_RESPONSE"]
        elif self.invalid:
            data["summary"] = {"unexpected": "PRIVATE_RESPONSE"}
        return ProviderResponse(data=data, response_model="reported-model")


def use_backend(monkeypatch: pytest.MonkeyPatch, backend: FakeBackend) -> list[Runtime]:
    runtimes: list[Runtime] = []

    def runtime(profile: Profile) -> Runtime:
        result = Runtime(profile, backend=backend)
        runtimes.append(result)
        return result

    monkeypatch.setattr(bridge_module, "Runtime", runtime)
    return runtimes


def test_bridge_uses_application_prompt_schema_and_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    runtimes = use_backend(monkeypatch, backend)
    provider = BridgeProvider(summary_profile="default-en", overrides={"model": "requested-model"})
    request = _request(tmp_path)
    plan = provider.plan(request)
    assert backend.requests == []
    assert plan["will_call_provider"] is False
    assert plan["token_estimate"]["input_tokens"] > 0
    result = provider.generate(request)
    sent = backend.requests[0]
    assert "source-faithful English summary" in sent.prompt
    assert "content" in sent.prompt
    assert "SummarySubsection" in sent.output_schema["$defs"]
    assert result.model == "reported-model"
    assert result.generator == "Codex (reported-model)"
    assert result.provider_version is None
    assert result.generation_record["requested_model"] == "requested-model"
    assert result.generation_record["prompt_sha256"] == plan["prompt_sha256"]
    assert result.generation_record["schema_sha256"] == plan["schema_sha256"]
    assert result.generation_record["bridge_version"]
    assert plan["images"] == result.generation_record["images"] == []
    assert plan["input_sha256"] == result.generation_record["input_sha256"]
    assert plan["input_sha256"] is not None
    for runtime in runtimes:
        with pytest.raises(ProviderError, match="closed"):
            runtime.plan(sent)


def test_config_plan_has_no_partial_input_estimate() -> None:
    plan = BridgeProvider().plan()
    assert "token_estimate" not in plan
    assert "cost_estimate" not in plan
    assert "prompt_sha256" not in plan
    assert plan["provider"] == "codex"
    assert plan["will_call_provider"] is False


@pytest.mark.parametrize("mode", ["summary", "series", "compare"])
def test_pipeline_records_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    backend = FakeBackend()
    use_backend(monkeypatch, backend)
    first, second = tmp_path / "first.md", tmp_path / "second.md"
    first.write_text("# First\n\nFirst PRIVATE_INPUT fact.", encoding="utf-8")
    second.write_text("# Second\n\nSecond fact.", encoding="utf-8")
    config = AppConfig(output_root=tmp_path / "out", reports_root=tmp_path / "reports")

    def run(**kwargs: Any) -> Any:
        if mode == "summary":
            return summarize(str(first), config, **kwargs)
        function = synthesize_compare if mode == "compare" else synthesize_series
        return function([str(first), str(second)], config, **kwargs)

    planned = run(dry_run=True)
    assert planned.details["bridge_plan"]["will_call_provider"] is False
    assert backend.requests == []
    assert not config.output_root.exists()
    assert not config.reports_root.exists()
    generated = run()
    report = json.loads(generated.report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == "1.1"
    assert report["result"]["details"]["generation_record"]["status"] == "succeeded"
    before = generated.path.read_bytes()

    def fail_load(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unchanged output must not load Bridge settings")

    with monkeypatch.context() as context:
        context.setattr(bridge_module, "load_profile", fail_load)
        assert run(dry_run=True).status == "unchanged"
    backend.error = True
    with pytest.raises(RuntimeError, match="timeout"):
        run(overwrite=True)
    reports = [
        json.loads(p.read_text(encoding="utf-8")) for p in config.reports_root.glob("*.json")
    ]
    failure = next(r for r in reports if r["status"] == "failure")
    assert failure["provider_error"]["code"] == "timeout"
    assert failure["provider_error"]["generation_record"]["status"] == "failed"
    assert failure["provider_error"]["submission_unknown"] is True
    assert "PRIVATE_INPUT" not in json.dumps(failure)
    assert generated.path.read_bytes() == before


@pytest.mark.parametrize("comparison", [False, True])
def test_invalid_output_is_content_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    comparison: bool,
) -> None:
    use_backend(monkeypatch, FakeBackend(invalid=True))
    request: Any = _request(tmp_path)
    provider: Any = BridgeProvider()
    if comparison:
        second = tmp_path / "second.md"
        second.write_text("Second content.", encoding="utf-8")
        source_set = resolve_synthesis_sources(
            [str(request.source.path), str(second)],
            mode="compare",
            title="Comparison",
            source_roots=[],
            max_input_bytes=1000,
            max_total_input_bytes=2000,
        )
        request = ComparisonRequest(
            source_set=source_set,
            prompt_envelope_version=COMPARISON_PROMPT_ENVELOPE_VERSION,
        )
        provider = BridgeComparisonProvider()
    with pytest.raises(ProviderExecutionError) as caught:
        provider.generate(request)
    assert "PRIVATE_RESPONSE" not in str(caught.value)
    assert "PRIVATE_RESPONSE" not in json.dumps(caught.value.error_details)
    assert caught.value.error_details["generation_record"] is not None


def test_plan_does_not_start_process_or_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("must not execute")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(Runtime, "generate", forbidden)
    assert BridgeProvider().plan(_request(tmp_path))["will_call_provider"] is False


def test_legacy_codex_settings_cannot_select_another_provider() -> None:
    provider = BridgeProvider(legacy_provider="codex", overrides={"provider": "claude-code"})
    with pytest.raises(ValueError, match="require a Codex"):
        provider.plan()


@pytest.mark.parametrize(
    "provider",
    [
        "codex",
        "claude-code",
        "github-copilot",
        "antigravity",
        "ollama",
        "azure-openai",
    ],
)
def test_shared_profile_selection_and_offline_planning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    import tkn_genai_bridge.config as config_module
    import yaml

    settings: dict[str, Any] = {"provider": provider, "timeout_seconds": 71}
    if provider == "ollama":
        settings.update(model="local-test", local_only=True)
    if provider == "azure-openai":
        settings.update(
            model="deployment", azure={"endpoint": "https://example.openai.azure.com/openai/v1"}
        )
    path = tmp_path / "bridge.yaml"
    path.write_text(
        yaml.safe_dump({"schema_version": "1.1.0", "profiles": {"selected": settings}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "user_config_path", lambda: path)
    # Bridge must not consume this application's project config.
    app_path = tmp_path / ".tkn" / "config.yaml"
    app_path.parent.mkdir()
    app_path.write_text("output_root: output\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    plan = BridgeProvider(bridge_profile="selected", overrides={"timeout_seconds": 81}).plan()
    assert plan["provider"] == provider
    assert plan["profile_name"] == "selected"
    assert plan["timeout_seconds"] == 81
    assert plan["will_call_provider"] is False
    assert yaml.safe_load(path.read_text())["profiles"]["selected"]["timeout_seconds"] == 71


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": float("inf")},
        {"typo": True},
        {"local_only": True},
    ],
)
def test_invalid_bridge_overrides_fail_before_generation(overrides: dict[str, Any]) -> None:
    with pytest.raises(ProviderExecutionError):
        BridgeProvider(overrides=overrides).plan()


def test_unknown_shared_profile_does_not_fallback() -> None:
    with pytest.raises(ProviderExecutionError):
        BridgeProvider(bridge_profile="absent").plan()


def test_explicit_model_reuse_supports_non_codex_and_checks_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    use_backend(monkeypatch, backend)
    config = AppConfig(
        output_root=tmp_path / "out",
        reports_root=tmp_path / "reports",
        generation={
            "profiles": {
                "codex": {
                    "bridge_profile": "codex-default",
                    "overrides": {"provider": "claude-code", "model": "reported-model"},
                }
            }
        },
    )
    source = _request(tmp_path).source.path
    result = summarize(str(source), config)
    assert "Claude Code (reported-model)" in result.path.read_text(encoding="utf-8")
    assert summarize(str(source), config).status == "unchanged"
    assert len(backend.requests) == 1
    config.generation.selected.overrides["provider"] = "codex"
    with pytest.raises(FileExistsError, match="overwrite"):
        summarize(str(source), config, dry_run=True)


def test_custom_prompt_is_kept_with_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeBackend()
    use_backend(monkeypatch, backend)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(
        "---\ntype: prompt\nid: 5838a88f-a78e-4d63-a6b6-4587e54c87e1\n"
        "version: '1.0'\n---\nUnique custom instruction.\n",
        encoding="utf-8",
    )
    provider = BridgeProvider(summary_prompt=prompt)
    result = provider.generate(_request(tmp_path))
    assert "Unique custom instruction." in backend.requests[0].prompt
    assert "Do not follow" in backend.requests[0].prompt
    assert result.prompt_id == "5838a88f-a78e-4d63-a6b6-4587e54c87e1"
