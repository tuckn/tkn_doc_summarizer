"""Adapt document resources to the shared generation runtime."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from tkn_genai_bridge import (
    GenAIError,
    GenerationRequest,
    GenerationResult,
    Profile,
    ProviderError,
    Runtime,
    load_profile,
)
from tkn_genai_bridge.models import PROVIDER_NAMES

from doc_summarizer.comparison_resources import load_comparison_profile
from doc_summarizer.config import DEFAULT_SUMMARY_PROFILE
from doc_summarizer.models import (
    ComparisonDocument,
    ComparisonRequest,
    SummaryDocument,
    SummaryGenerationRequest,
)
from doc_summarizer.prompting import (
    load_summary_prompt,
    render_comparison_prompt,
    render_summary_prompt,
)
from doc_summarizer.providers.base import (
    ComparisonProviderResult,
    ProviderExecutionError,
    ProviderResult,
)
from doc_summarizer.summary_resources import load_summary_profile
from doc_summarizer.validation import validate_comparison_document

logger = logging.getLogger(__name__)


def _execution_error(exc: GenAIError) -> ProviderExecutionError:
    details: dict[str, Any] = {
        "code": exc.code,
        "generation_record": exc.record.model_dump(mode="json") if exc.record else None,
    }
    if isinstance(exc, ProviderError):
        details.update(
            http_status=exc.http_status,
            retry_after_seconds=exc.retry_after_seconds,
            retryable=exc.retryable,
            submission_unknown=exc.submission_unknown,
        )
    return ProviderExecutionError(
        f"Generation failed ({exc.code}): {exc}",
        error_details=details,
    )


class _BridgeConnection:
    def __init__(
        self,
        *,
        bridge_profile: str = "codex-default",
        overrides: dict[str, Any] | None = None,
        legacy_provider: str | None = None,
    ) -> None:
        self.bridge_profile = bridge_profile
        self.overrides = deepcopy(overrides or {})
        self.legacy_provider = legacy_provider

    def connection(self) -> Profile:
        # Reusing an unchanged note does not need shared settings or a runtime.
        profile = load_profile(self.bridge_profile, overrides=self.overrides)
        if self.legacy_provider is not None and (
            self.legacy_provider != "codex" or profile.provider != "codex"
        ):
            raise ValueError(
                "legacy provider/codex_executable settings require a Codex Bridge profile; "
                "remove them and select the connection with bridge_profile"
            )
        return profile

    def requested_generator(self, model: str) -> str:
        return f"{PROVIDER_NAMES[self.connection().provider]} ({model})"

    def _plan(self, request: GenerationRequest, *, complete: bool) -> dict[str, Any]:
        try:
            connection = self.connection()
            with Runtime(connection) as runtime:
                plan = runtime.plan(request).model_dump(mode="json")
        except GenAIError as exc:
            raise _execution_error(exc) from exc
        if complete:
            return plan
        # Config inspection has no document input; do not estimate a partial prompt.
        return {
            key: plan[key]
            for key in (
                "provider",
                "model",
                "profile_name",
                "bridge_version",
                "generation_settings_sha256",
                "timeout_seconds",
                "will_call_provider",
                "local_only",
            )
        } | {
            "reasoning_effort": connection.reasoning_effort,
            "max_output_tokens": connection.max_output_tokens,
        }

    def _generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            with Runtime(self.connection()) as runtime:
                return runtime.generate(request)
        except GenAIError as exc:
            raise _execution_error(exc) from exc

    @staticmethod
    def _metadata(result: GenerationResult) -> dict[str, Any]:
        model = result.record.response_model or result.record.requested_model
        name = PROVIDER_NAMES[result.record.provider]
        generator = f"{name} ({model})" if model else name
        logger.info("Generator: %s", generator)
        return {
            "provider": result.record.provider,
            "model": model,
            "generator": generator,
            "provider_version": None,
            "generation_record": result.record.model_dump(mode="json"),
        }

    @staticmethod
    def _invalid_output(result: GenerationResult) -> ProviderExecutionError:
        return ProviderExecutionError(
            "Generated output failed the application's document contract",
            error_details={
                "code": "document_validation",
                "generation_record": result.record.model_dump(mode="json"),
            },
        )


class BridgeProvider(_BridgeConnection):
    def __init__(
        self,
        *,
        bridge_profile: str = "codex-default",
        overrides: dict[str, Any] | None = None,
        legacy_provider: str | None = None,
        summary_profile: str = DEFAULT_SUMMARY_PROFILE,
        summary_prompt: Path | None = None,
    ) -> None:
        super().__init__(
            bridge_profile=bridge_profile,
            overrides=overrides,
            legacy_provider=legacy_provider,
        )
        self.prompt = load_summary_prompt(summary_prompt, profile_name=summary_profile)
        self.profile = load_summary_profile(summary_profile, prompt=self.prompt)

    def _request(self, request: SummaryGenerationRequest | None) -> GenerationRequest:
        return GenerationRequest(
            prompt=render_summary_prompt(self.prompt, request)
            if request
            else self.prompt.instructions,
            output_schema=self.profile.schema.value,
            schema_name="document_summary",
        )

    def plan(self, request: SummaryGenerationRequest | None = None) -> dict[str, Any]:
        return self._plan(self._request(request), complete=request is not None)

    def generate(self, request: SummaryGenerationRequest) -> ProviderResult:
        result = self._generate(self._request(request))
        try:
            document = SummaryDocument.model_validate(result.data)
        except ValueError:
            # Pydantic errors can include response values; suppress the unsafe cause.
            raise self._invalid_output(result) from None
        return ProviderResult(
            document=document,
            prompt_id=self.prompt.prompt_id,
            prompt_version=self.prompt.version,
            prompt_envelope_version=request.prompt_envelope_version,
            prompt_source=self.prompt.source,
            prompt_sha256=self.prompt.sha256,
            **self._metadata(result),
        )


class BridgeComparisonProvider(_BridgeConnection):
    def __init__(
        self,
        *,
        bridge_profile: str = "codex-default",
        overrides: dict[str, Any] | None = None,
        legacy_provider: str | None = None,
        summary_profile: str = DEFAULT_SUMMARY_PROFILE,
    ) -> None:
        super().__init__(
            bridge_profile=bridge_profile,
            overrides=overrides,
            legacy_provider=legacy_provider,
        )
        self.profile = load_comparison_profile(summary_profile)
        self.prompt = self.profile.prompt

    def _request(self, request: ComparisonRequest | None) -> GenerationRequest:
        return GenerationRequest(
            prompt=(
                render_comparison_prompt(self.prompt, request)
                if request
                else self.prompt.instructions
            ),
            output_schema=self.profile.schema.value,
            schema_name="document_comparison",
        )

    def plan(self, request: ComparisonRequest | None = None) -> dict[str, Any]:
        return self._plan(self._request(request), complete=request is not None)

    def generate(self, request: ComparisonRequest) -> ComparisonProviderResult:
        result = self._generate(self._request(request))
        try:
            document = ComparisonDocument.model_validate(result.data)
            errors = validate_comparison_document(
                document,
                source_ids={source.id for source in request.source_set.sources},
            )
            if errors:
                raise ValueError("invalid comparison source references")
        except ValueError:
            raise self._invalid_output(result) from None
        return ComparisonProviderResult(
            document=document,
            prompt_id=self.prompt.prompt_id,
            prompt_version=self.prompt.version,
            prompt_envelope_version=request.prompt_envelope_version,
            prompt_source=self.prompt.source,
            prompt_sha256=self.prompt.sha256,
            **self._metadata(result),
        )
