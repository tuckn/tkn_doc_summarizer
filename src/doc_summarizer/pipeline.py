"""Summary pipeline orchestration."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from doc_summarizer.config import AppConfig, SourcePathFormat
from doc_summarizer.context import context_sha256, load_context
from doc_summarizer.conversation import (
    request_sources,
    validate_conversation_date,
    validate_conversation_document,
)
from doc_summarizer.io import atomic_write, sha256_bytes
from doc_summarizer.meeting_minutes import validate_meeting_minutes_document
from doc_summarizer.models import (
    ComparisonRequest,
    ConversationDocument,
    DocumentSource,
    DocumentSourceSet,
    GeneratedSummaryDocument,
    MeetingMinutesDocument,
    SeriesSummaryRequest,
    SummaryGenerationRequest,
    SummaryRequest,
    SummaryResult,
)
from doc_summarizer.naming import build_output_path
from doc_summarizer.notes import (
    REVIEW_STATUSES,
    render_comparison_summary,
    render_series_summary,
    render_summary,
    source_reference_format,
    source_reference_to_path,
)
from doc_summarizer.prompting import (
    COMPARISON_PROMPT_ENVELOPE_VERSION,
    CONVERSATION_PROMPT_ENVELOPE_VERSION,
    MEETING_MINUTES_PROMPT_ENVELOPE_VERSION,
    PROMPT_ENVELOPE_VERSION,
    SERIES_PROMPT_ENVELOPE_VERSION,
)
from doc_summarizer.providers import (
    BridgeComparisonProvider,
    BridgeProvider,
    ComparisonProvider,
    ProviderExecutionError,
    SummaryProvider,
)
from doc_summarizer.source import resolve_source, split_frontmatter
from doc_summarizer.synthesis import resolve_synthesis_sources, source_set_sha256
from doc_summarizer.validation import (
    validate_comparison_document,
    validate_summary,
    validate_summary_text,
)

logger = logging.getLogger(__name__)


def _summary_envelope(profile_name: str, *, series: bool = False) -> str:
    if profile_name == "meeting-minutes-ja":
        return MEETING_MINUTES_PROMPT_ENVELOPE_VERSION
    if profile_name == "conversation-ja":
        return CONVERSATION_PROMPT_ENVELOPE_VERSION
    return SERIES_PROMPT_ENVELOPE_VERSION if series else PROMPT_ENVELOPE_VERSION


def _validate_generated_summary(
    document: GeneratedSummaryDocument,
    profile_name: str,
    request: SummaryGenerationRequest,
) -> None:
    if (
        isinstance(document, ConversationDocument) != (profile_name == "conversation-ja")
        or isinstance(document, MeetingMinutesDocument) != (profile_name == "meeting-minutes-ja")
    ):
        raise RuntimeError("provider returned a document type that does not match the profile")
    if isinstance(document, ConversationDocument) and validate_conversation_document(
        document, sources=request_sources(request)
    ):
        raise RuntimeError("generated conversation evidence validation failed")
    if isinstance(document, MeetingMinutesDocument) and validate_meeting_minutes_document(
        document,
        source_ids=set(request_sources(request)),
        has_context=request.context is not None,
    ):
        raise RuntimeError("generated meeting minutes attribution validation failed")


def _check_total_context(
    source_set: DocumentSourceSet, context: str | None, config: AppConfig
) -> None:
    total = sum(entry.document.source_size_bytes for entry in source_set.sources)
    total += len(context.encode("utf-8")) if context else 0
    if total > config.max_total_input_bytes:
        raise ValueError("sources and context exceed max_total_input_bytes")


def _source_set_with_title(
    source_set: DocumentSourceSet,
    title: str,
) -> DocumentSourceSet:
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("generated synthesis title must not be empty")
    titled = source_set.model_copy(update={"title": clean_title})
    return titled.model_copy(update={"source_set_sha256": source_set_sha256(titled)})


def provider_for_config(config: AppConfig) -> SummaryProvider:
    return BridgeProvider(
        bridge_profile=config.generation.summary.selected.bridge_profile,
        overrides=config.generation.summary.selected.overrides,
        summary_profile=config.summary_profile,
        summary_prompt=config.summary_prompt,
    )


def comparison_provider_for_config(
    config: AppConfig, *, comparison_profile: str | None = None
) -> ComparisonProvider:
    return BridgeComparisonProvider(
        bridge_profile=config.generation.comparison.selected.bridge_profile,
        overrides=config.generation.comparison.selected.overrides,
        comparison_profile=(
            comparison_profile
            if comparison_profile is not None
            else config.generation.comparison.selected.comparison_profile
        ),
    )


def _requested_generator(
    provider: SummaryProvider | ComparisonProvider,
    config: AppConfig,
    *,
    comparison: bool = False,
) -> str | None:
    selected = (
        config.generation.comparison.selected if comparison else config.generation.summary.selected
    )
    model = selected.overrides.get("model")
    if not isinstance(model, str):
        return None
    if isinstance(provider, BridgeProvider | BridgeComparisonProvider):
        return provider.requested_generator(model)
    return f"Codex ({model})"


def _candidate_metadata(path: Path) -> dict[str, Any] | None:
    try:
        metadata, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return metadata


def _find_existing(
    output_root: Path,
    *,
    source_path: Path,
    profile_name: str,
    prompt_id: str,
) -> Path | None:
    if not output_root.is_dir():
        return None
    matches: list[Path] = []
    for candidate in output_root.rglob("*.md"):
        metadata = _candidate_metadata(candidate)
        if metadata is None:
            continue
        try:
            same_source = source_reference_to_path(str(metadata.get("source") or "")).resolve() == (
                source_path.resolve()
            )
        except ValueError:
            same_source = False
        if (
            same_source
            and str(metadata.get("summaryProfile") or "") == profile_name
            and str(metadata.get("promptId") or "") == prompt_id
        ):
            matches.append(candidate)
    if len(matches) > 1:
        raise FileExistsError(
            "multiple summaries share the same source, summaryProfile, and promptId: "
            + ", ".join(str(path) for path in sorted(matches))
        )
    return matches[0] if matches else None


def _target_path(
    source: DocumentSource,
    config: AppConfig,
    provider: SummaryProvider,
    explicit_output: Path | None,
    conversation_date: str | None = None,
) -> Path:
    if explicit_output is not None:
        target = explicit_output.expanduser()
        target = target if target.is_absolute() else (Path.cwd() / target).resolve()
        if target.suffix.lower() != ".md":
            raise ValueError("--output must use the .md extension")
        return target
    existing = _find_existing(
        config.output_root,
        source_path=source.path,
        profile_name=provider.profile.name,
        prompt_id=provider.prompt.prompt_id,
    )
    if existing:
        return existing
    return build_output_path(
        config.output_root,
        source_path=source.path,
        published=conversation_date
        if provider.profile.name in ("conversation-ja", "meeting-minutes-ja")
        else source.published,
        title=source.title,
        profile_name=provider.profile.name,
        prompt_id=provider.prompt.prompt_id,
    )


def _validate_existing_identity(
    metadata: dict[str, Any],
    *,
    source_path: Path,
    profile_name: str,
    prompt_id: str,
    target: Path,
) -> None:
    try:
        same_source = source_reference_to_path(str(metadata.get("source") or "")).resolve() == (
            source_path.resolve()
        )
    except ValueError:
        same_source = False
    if (
        not same_source
        or str(metadata.get("summaryProfile") or "") != profile_name
        or str(metadata.get("promptId") or "") != prompt_id
    ):
        raise FileExistsError(
            "refusing to replace an output that belongs to another source, "
            f"summary profile, or prompt: {target}"
        )


def _is_current(
    metadata: dict[str, Any],
    *,
    source: DocumentSource,
    prompt_version: str,
    prompt_sha256: str,
    profile_sha256: str,
    requested_generator: str | None,
    source_path_format: SourcePathFormat,
    context: str | None = None,
) -> bool:
    generator = str(metadata.get("generator") or "")
    model_matches = requested_generator is None or generator == requested_generator
    return (
        metadata.get("sourceSha256") == source.source_sha256
        and source_reference_format(str(metadata.get("source") or "")) == source_path_format
        and str(metadata.get("promptVersion") or "") == prompt_version
        and metadata.get("promptSha256") == prompt_sha256
        and metadata.get("summaryProfileSha256") == profile_sha256
        and metadata.get("promptEnvelopeVersion")
        == _summary_envelope(str(metadata.get("summaryProfile")))
        and metadata.get("contextSha256") == context_sha256(context)
        and model_matches
    )


def _write_report(
    config: AppConfig,
    *,
    started_at: datetime,
    status: str,
    result: SummaryResult | None = None,
    error: str | None = None,
    command: str = "summarize",
    provider_error: dict[str, Any] | None = None,
) -> Path:
    now = datetime.now().astimezone()
    run_id = f"{now.strftime('%Y%m%dT%H%M%S%z')}_{uuid.uuid4().hex[:8]}"
    path = config.reports_root / f"{run_id}.json"
    payload: dict[str, object] = {
        "schema_version": "1.1",
        "run_id": run_id,
        "command": command,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": now.isoformat(timespec="seconds"),
        "status": status,
        "error": error,
        "provider_error": provider_error,
        "result": None,
    }
    if result is not None:
        payload["result"] = {
            "path": str(result.path),
            "source_path": str(result.source_path),
            "status": result.status,
            "details": result.details,
        }
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    logger.debug("Run report written: %s", path)
    return path


def _summarize(
    source_value: str,
    config: AppConfig,
    *,
    provider: SummaryProvider,
    explicit_output: Path | None,
    overwrite: bool,
    dry_run: bool,
    conversation_date: str | None,
    context: str | None,
) -> SummaryResult:
    conversation_date = validate_conversation_date(conversation_date)
    is_meeting = provider.profile.name in ("conversation-ja", "meeting-minutes-ja")
    if conversation_date is not None and not is_meeting:
        raise ValueError("--conversation-date requires conversation-ja or meeting-minutes-ja")
    envelope_version = _summary_envelope(provider.profile.name)
    source = resolve_source(
        source_value,
        source_roots=config.source_roots,
        max_input_bytes=config.max_input_bytes,
    )
    prompt = provider.prompt
    profile = provider.profile
    target = _target_path(source, config, provider, explicit_output, conversation_date)
    existing_metadata: dict[str, Any] | None = None
    if target.exists():
        existing_metadata = _candidate_metadata(target)
        if existing_metadata is None:
            raise FileExistsError(f"existing output is not a readable generated summary: {target}")
        _validate_existing_identity(
            existing_metadata,
            source_path=source.path,
            profile_name=profile.name,
            prompt_id=prompt.prompt_id,
            target=target,
        )
        existing_errors = validate_summary(target)
        current = _is_current(
            existing_metadata,
            source=source,
            prompt_version=prompt.version,
            prompt_sha256=prompt.sha256,
            profile_sha256=profile.sha256,
            requested_generator=_requested_generator(provider, config),
            source_path_format=config.source_path_format,
            context=context,
        )
        current = current and (
            not is_meeting or existing_metadata.get("conversationDate") == conversation_date
        )
        if current and not existing_errors and not overwrite:
            logger.info("Summary note is already current: %s", target)
            return SummaryResult(
                path=target,
                source_path=source.path,
                status="unchanged",
                details={
                    "validated": True,
                    "source_sha256": source.source_sha256,
                    "prompt_id": prompt.prompt_id,
                    "prompt_version": prompt.version,
                    "prompt_sha256": prompt.sha256,
                    "summary_profile": profile.name,
                    "summary_profile_sha256": profile.sha256,
                    "source_path_format": config.source_path_format,
                    "context_sha256": context_sha256(context),
                    "dry_run": dry_run,
                },
            )
        if not overwrite:
            reason = (
                "; ".join(existing_errors)
                if existing_errors
                else "source, context, prompt, or explicitly selected model changed"
            )
            raise FileExistsError(
                f"existing summary requires explicit --overwrite ({reason}): {target}"
            )
        review_status = str(existing_metadata.get("reviewStatus") or "")
        if review_status in REVIEW_STATUSES and review_status != "unreviewed":
            logger.warning(
                "Overwriting a %s summary resets reviewStatus to unreviewed: %s",
                review_status,
                target,
            )
    request = SummaryRequest(
        source=source,
        prompt_envelope_version=envelope_version,
        conversation_date=conversation_date,
        context=context,
    )
    if dry_run:
        action = "updated" if target.exists() else "created"
        logger.info("Dry run: summary would be %s at %s", action, target)
        return SummaryResult(
            path=target,
            source_path=source.path,
            status="planned",
            details={
                "planned_status": action,
                "bridge_plan": provider.plan(request),
                "source_sha256": source.source_sha256,
                "prompt_id": prompt.prompt_id,
                "prompt_version": prompt.version,
                "prompt_sha256": prompt.sha256,
                "summary_profile": profile.name,
                "summary_profile_sha256": profile.sha256,
                "source_path_format": config.source_path_format,
                "context_sha256": context_sha256(context),
                "dry_run": True,
            },
        )
    logger.info("Generating structured summary with the configured provider")
    generated = provider.generate(request)
    if (
        generated.prompt_id != prompt.prompt_id
        or generated.prompt_version != prompt.version
        or generated.prompt_sha256 != prompt.sha256
        or generated.prompt_envelope_version != envelope_version
    ):
        raise RuntimeError("provider returned prompt provenance that does not match the request")
    _validate_generated_summary(generated.document, profile.name, request)
    now = datetime.now().astimezone()
    note_id = (
        str(existing_metadata.get("noteId"))
        if existing_metadata and existing_metadata.get("noteId")
        else None
    )
    created_at = (
        str(existing_metadata.get("created") or existing_metadata.get("date"))
        if existing_metadata and (existing_metadata.get("created") or existing_metadata.get("date"))
        else None
    )
    text = render_summary(
        source=source,
        document=generated.document,
        now=now,
        generator=generated.generator,
        profile=profile,
        prompt_envelope_version=envelope_version,
        source_path_format=config.source_path_format,
        note_id=note_id,
        created_at=created_at,
        conversation_date=conversation_date,
        context_sha256=context_sha256(context),
    )
    errors = validate_summary_text(text)
    if errors:
        raise RuntimeError("generated summary validation failed: " + "; ".join(errors))
    status = atomic_write(target, text, overwrite=overwrite)
    persisted_errors = validate_summary(target)
    if persisted_errors:
        raise RuntimeError("persisted summary validation failed: " + "; ".join(persisted_errors))
    logger.info("Summary note %s: %s", status, target)
    return SummaryResult(
        path=target,
        source_path=source.path,
        status=status,
        details={
            "validated": True,
            "provider": generated.provider,
            "model": generated.model,
            "provider_version": generated.provider_version,
            "generation_record": generated.generation_record,
            "source_sha256": source.source_sha256,
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.version,
            "prompt_sha256": prompt.sha256,
            "prompt_envelope_version": envelope_version,
            "prompt_source": prompt.source,
            "summary_profile": profile.name,
            "summary_profile_source": profile.source,
            "summary_profile_sha256": profile.sha256,
            "source_path_format": config.source_path_format,
            "context_sha256": context_sha256(context),
            "output_schema_source": profile.schema.source,
            "output_schema_id": profile.schema.resource_id,
            "output_schema_version": profile.schema.version,
            "output_schema_sha256": profile.schema.sha256,
            "template_id": profile.template.template_id,
            "template_version": profile.template.version,
            "template_source": profile.template.source,
            "template_sha256": profile.template.sha256,
            "dry_run": False,
        },
    )


def summarize(
    source_value: str,
    config: AppConfig,
    *,
    explicit_output: Path | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    provider: SummaryProvider | None = None,
    conversation_date: str | None = None,
    context: str | list[str] | None = None,
) -> SummaryResult:
    context = load_context(context, max_input_bytes=config.max_input_bytes)
    started_at = datetime.now().astimezone()
    active_provider = provider or provider_for_config(config)
    try:
        result = _summarize(
            source_value,
            config,
            provider=active_provider,
            explicit_output=explicit_output,
            overwrite=overwrite,
            dry_run=dry_run,
            conversation_date=conversation_date,
            context=context,
        )
    except Exception as exc:
        if dry_run:
            raise
        report = _write_report(
            config,
            started_at=started_at,
            status="failure",
            error=str(exc),
            provider_error=exc.error_details if isinstance(exc, ProviderExecutionError) else None,
        )
        failure = RuntimeError(f"{exc}; report={report}")
        failure.report_path = report  # type: ignore[attr-defined]
        raise failure from exc
    if dry_run:
        return result
    report = _write_report(
        config,
        started_at=started_at,
        status="success",
        result=result,
    )
    return result.model_copy(update={"report_path": report})


def _find_existing_series(
    output_root: Path,
    *,
    source_set_id: str,
    profile_name: str,
    prompt_id: str,
) -> Path | None:
    if not output_root.is_dir():
        return None
    matches: list[Path] = []
    for candidate in output_root.rglob("*.md"):
        metadata = _candidate_metadata(candidate)
        if metadata is None:
            continue
        if (
            metadata.get("synthesisMode") == "series"
            and str(metadata.get("sourceSetId") or "") == source_set_id
            and str(metadata.get("summaryProfile") or "") == profile_name
            and str(metadata.get("promptId") or "") == prompt_id
        ):
            matches.append(candidate)
    if len(matches) > 1:
        raise FileExistsError(
            "multiple series summaries share the same sourceSetId, summaryProfile, and promptId: "
            + ", ".join(str(path) for path in sorted(matches))
        )
    return matches[0] if matches else None


def _series_target_path(
    source_set: DocumentSourceSet,
    config: AppConfig,
    provider: SummaryProvider,
    explicit_output: Path | None,
) -> Path:
    if explicit_output is not None:
        target = explicit_output.expanduser()
        target = target if target.is_absolute() else (Path.cwd() / target).resolve()
        if target.suffix.lower() != ".md":
            raise ValueError("--output must use the .md extension")
        return target
    existing = _find_existing_series(
        config.output_root,
        source_set_id=source_set.source_set_id,
        profile_name=provider.profile.name,
        prompt_id=provider.prompt.prompt_id,
    )
    if existing:
        return existing
    return build_output_path(
        config.output_root,
        source_path=source_set.sources[0].document.path,
        published=(
            source_set.conversation_date
            if provider.profile.name in ("conversation-ja", "meeting-minutes-ja")
            else source_set.published
        ),
        title=source_set.title,
        profile_name=provider.profile.name,
        prompt_id=provider.prompt.prompt_id,
        identity_suffix=uuid.UUID(source_set.source_set_id).hex[:8],
    )


def _validate_existing_series_identity(
    metadata: dict[str, Any],
    *,
    source_set_id: str,
    profile_name: str,
    prompt_id: str,
    target: Path,
) -> None:
    if (
        metadata.get("synthesisMode") != "series"
        or str(metadata.get("sourceSetId") or "") != source_set_id
        or str(metadata.get("summaryProfile") or "") != profile_name
        or str(metadata.get("promptId") or "") != prompt_id
    ):
        raise FileExistsError(
            "refusing to replace an output that belongs to another source set, "
            f"synthesis mode, summary profile, or prompt: {target}"
        )


def _is_current_series(
    metadata: dict[str, Any],
    *,
    source_set: DocumentSourceSet,
    prompt_version: str,
    prompt_sha256: str,
    profile_sha256: str,
    requested_generator: str | None,
    source_path_format: SourcePathFormat,
    context: str | None = None,
) -> bool:
    generator = str(metadata.get("generator") or "")
    model_matches = requested_generator is None or generator == requested_generator
    sources = metadata.get("sources")
    format_matches = isinstance(sources, list) and all(
        isinstance(entry, dict)
        and source_reference_format(str(entry.get("source") or "")) == source_path_format
        for entry in sources
    )
    return (
        str(metadata.get("title") or "") == source_set.title
        and metadata.get("sourceSetSha256") == source_set.source_set_sha256
        and str(metadata.get("promptVersion") or "") == prompt_version
        and metadata.get("promptSha256") == prompt_sha256
        and metadata.get("summaryProfileSha256") == profile_sha256
        and metadata.get("promptEnvelopeVersion")
        == _summary_envelope(str(metadata.get("summaryProfile")), series=True)
        and metadata.get("contextSha256") == context_sha256(context)
        and model_matches
        and format_matches
    )


def _series_details(
    source_set: DocumentSourceSet,
    provider: SummaryProvider,
    *,
    dry_run: bool,
    source_path_format: SourcePathFormat,
    generated_title_pending: bool = False,
    context: str | None = None,
) -> dict[str, object]:
    prompt = provider.prompt
    profile = provider.profile
    return {
        **(
            {"conversation_date": source_set.conversation_date}
            if profile.name in ("conversation-ja", "meeting-minutes-ja")
            else {}
        ),
        "validated": not dry_run,
        "synthesis_mode": "series",
        "source_set_id": source_set.source_set_id,
        "source_set_sha256": source_set.source_set_sha256,
        "source_count": len(source_set.sources),
        "source_paths": [str(entry.document.path) for entry in source_set.sources],
        "source_path_format": source_path_format,
        "context_sha256": context_sha256(context),
        "title": source_set.title,
        "generated_title_pending": generated_title_pending,
        "prompt_id": prompt.prompt_id,
        "prompt_version": prompt.version,
        "prompt_sha256": prompt.sha256,
        "summary_profile": profile.name,
        "summary_profile_sha256": profile.sha256,
        "dry_run": dry_run,
    }


def _synthesize_series(
    source_values: list[str],
    config: AppConfig,
    *,
    title: str | None,
    provider: SummaryProvider,
    explicit_output: Path | None,
    overwrite: bool,
    dry_run: bool,
    conversation_date: str | None,
    context: str | None,
) -> SummaryResult:
    conversation_date = validate_conversation_date(conversation_date)
    is_meeting = provider.profile.name in ("conversation-ja", "meeting-minutes-ja")
    if conversation_date is not None and not is_meeting:
        raise ValueError("--conversation-date requires conversation-ja or meeting-minutes-ja")
    envelope_version = _summary_envelope(provider.profile.name, series=True)
    source_set = resolve_synthesis_sources(
        source_values,
        mode="series",
        title=title,
        source_roots=config.source_roots,
        max_input_bytes=config.max_input_bytes,
        max_total_input_bytes=config.max_total_input_bytes,
    )
    _check_total_context(source_set, context, config)
    if is_meeting:
        source_set = source_set.model_copy(update={"conversation_date": conversation_date})
        source_set = source_set.model_copy(
            update={"source_set_sha256": source_set_sha256(source_set)}
        )
    prompt = provider.prompt
    profile = provider.profile
    automatic_existing = (
        _find_existing_series(
            config.output_root,
            source_set_id=source_set.source_set_id,
            profile_name=profile.name,
            prompt_id=prompt.prompt_id,
        )
        if explicit_output is None
        else None
    )
    generated_target_pending = (
        title is None and explicit_output is None and automatic_existing is None
    )
    target = _series_target_path(source_set, config, provider, explicit_output)
    existing_metadata: dict[str, Any] | None = None
    if target.exists() and not generated_target_pending:
        existing_metadata = _candidate_metadata(target)
        if existing_metadata is None:
            raise FileExistsError(f"existing output is not a readable generated summary: {target}")
        _validate_existing_series_identity(
            existing_metadata,
            source_set_id=source_set.source_set_id,
            profile_name=profile.name,
            prompt_id=prompt.prompt_id,
            target=target,
        )
        if title is None:
            stored_title = str(existing_metadata.get("title") or "").strip()
            if not stored_title:
                raise RuntimeError(f"existing series summary has no usable title: {target}")
            source_set = _source_set_with_title(source_set, stored_title)
        existing_errors = validate_summary(target)
        current = _is_current_series(
            existing_metadata,
            source_set=source_set,
            prompt_version=prompt.version,
            prompt_sha256=prompt.sha256,
            profile_sha256=profile.sha256,
            requested_generator=_requested_generator(provider, config),
            source_path_format=config.source_path_format,
            context=context,
        )
        if current and not existing_errors and not overwrite:
            logger.info("Series summary note is already current: %s", target)
            return SummaryResult(
                path=target,
                source_path=source_set.sources[0].document.path,
                status="unchanged",
                details=_series_details(
                    source_set,
                    provider,
                    dry_run=dry_run,
                    source_path_format=config.source_path_format,
                    context=context,
                ),
            )
        if not overwrite:
            reason = (
                "; ".join(existing_errors)
                if existing_errors
                else "source set, context, prompt, or explicitly selected model changed"
            )
            raise FileExistsError(
                f"existing series summary requires explicit --overwrite ({reason}): {target}"
            )
        review_status = str(existing_metadata.get("reviewStatus") or "")
        if review_status in REVIEW_STATUSES and review_status != "unreviewed":
            logger.warning(
                "Overwriting a %s summary resets reviewStatus to unreviewed: %s",
                review_status,
                target,
            )
    request = SeriesSummaryRequest(
        source_set=source_set,
        prompt_envelope_version=envelope_version,
        context=context,
    )
    if dry_run:
        action = "updated" if target.exists() else "created"
        logger.info("Dry run: series summary would be %s at %s", action, target)
        details = _series_details(
            source_set,
            provider,
            dry_run=True,
            source_path_format=config.source_path_format,
            generated_title_pending=generated_target_pending,
            context=context,
        )
        details["planned_status"] = action
        details["bridge_plan"] = provider.plan(request)
        return SummaryResult(
            path=target,
            source_path=source_set.sources[0].document.path,
            status="planned",
            details=details,
        )
    logger.info(
        "Generating one structured summary from %d ordered sources", len(source_set.sources)
    )
    generated = provider.generate(request)
    if (
        generated.prompt_id != prompt.prompt_id
        or generated.prompt_version != prompt.version
        or generated.prompt_sha256 != prompt.sha256
        or generated.prompt_envelope_version != envelope_version
    ):
        raise RuntimeError("provider returned prompt provenance that does not match the request")
    _validate_generated_summary(generated.document, profile.name, request)
    if title is None:
        source_set = _source_set_with_title(source_set, generated.document.title)
        if generated_target_pending:
            target = _series_target_path(source_set, config, provider, explicit_output=None)
            if target.exists():
                raise FileExistsError(
                    "generated title resolves to an existing output that belongs to another "
                    f"summary: {target}"
                )
    now = datetime.now().astimezone()
    note_id = (
        str(existing_metadata.get("noteId"))
        if existing_metadata and existing_metadata.get("noteId")
        else None
    )
    created_at = (
        str(existing_metadata.get("created") or existing_metadata.get("date"))
        if existing_metadata and (existing_metadata.get("created") or existing_metadata.get("date"))
        else None
    )
    text = render_series_summary(
        source_set=source_set,
        document=generated.document,
        now=now,
        generator=generated.generator,
        profile=profile,
        prompt_envelope_version=envelope_version,
        source_path_format=config.source_path_format,
        note_id=note_id,
        created_at=created_at,
        context_sha256=context_sha256(context),
    )
    errors = validate_summary_text(text)
    if errors:
        raise RuntimeError("generated series summary validation failed: " + "; ".join(errors))
    status = atomic_write(target, text, overwrite=overwrite)
    persisted_errors = validate_summary(target)
    if persisted_errors:
        raise RuntimeError(
            "persisted series summary validation failed: " + "; ".join(persisted_errors)
        )
    logger.info("Series summary note %s: %s", status, target)
    details = _series_details(
        source_set,
        provider,
        dry_run=False,
        source_path_format=config.source_path_format,
        context=context,
    )
    details.update(
        {
            "provider": generated.provider,
            "model": generated.model,
            "provider_version": generated.provider_version,
            "generation_record": generated.generation_record,
            "prompt_envelope_version": envelope_version,
            "prompt_source": prompt.source,
            "summary_profile_source": profile.source,
            "output_schema_source": profile.schema.source,
            "output_schema_id": profile.schema.resource_id,
            "output_schema_version": profile.schema.version,
            "output_schema_sha256": profile.schema.sha256,
            "template_id": profile.template.template_id,
            "template_version": profile.template.version,
            "template_source": profile.template.source,
            "template_sha256": profile.template.sha256,
        }
    )
    return SummaryResult(
        path=target,
        source_path=source_set.sources[0].document.path,
        status=status,
        details=details,
    )


def synthesize_series(
    source_values: list[str],
    config: AppConfig,
    *,
    title: str | None = None,
    explicit_output: Path | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    provider: SummaryProvider | None = None,
    conversation_date: str | None = None,
    context: str | list[str] | None = None,
) -> SummaryResult:
    context = load_context(context, max_input_bytes=config.max_input_bytes)
    started_at = datetime.now().astimezone()
    active_provider = provider or provider_for_config(config)
    try:
        result = _synthesize_series(
            source_values,
            config,
            title=title,
            provider=active_provider,
            explicit_output=explicit_output,
            overwrite=overwrite,
            dry_run=dry_run,
            conversation_date=conversation_date,
            context=context,
        )
    except Exception as exc:
        if dry_run:
            raise
        report = _write_report(
            config,
            started_at=started_at,
            status="failure",
            error=str(exc),
            provider_error=exc.error_details if isinstance(exc, ProviderExecutionError) else None,
            command="summarize",
        )
        failure = RuntimeError(f"{exc}; report={report}")
        failure.report_path = report  # type: ignore[attr-defined]
        raise failure from exc
    if dry_run:
        return result
    report = _write_report(
        config,
        started_at=started_at,
        status="success",
        result=result,
        command="summarize",
    )
    return result.model_copy(update={"report_path": report})


def _find_existing_comparison(
    output_root: Path,
    *,
    source_set_id: str,
    profile_name: str,
    prompt_id: str,
) -> Path | None:
    if not output_root.is_dir():
        return None
    matches: list[Path] = []
    for candidate in output_root.rglob("*.md"):
        metadata = _candidate_metadata(candidate)
        if metadata is None:
            continue
        if (
            metadata.get("synthesisMode") == "compare"
            and str(metadata.get("sourceSetId") or "") == source_set_id
            and str(metadata.get("summaryProfile") or "") == profile_name
            and str(metadata.get("promptId") or "") == prompt_id
        ):
            matches.append(candidate)
    if len(matches) > 1:
        raise FileExistsError(
            "multiple comparisons share the same sourceSetId, summaryProfile, and promptId: "
            + ", ".join(str(path) for path in sorted(matches))
        )
    return matches[0] if matches else None


def _comparison_target_path(
    source_set: DocumentSourceSet,
    config: AppConfig,
    provider: ComparisonProvider,
    explicit_output: Path | None,
) -> Path:
    if explicit_output is not None:
        target = explicit_output.expanduser()
        target = target if target.is_absolute() else (Path.cwd() / target).resolve()
        if target.suffix.lower() != ".md":
            raise ValueError("--output must use the .md extension")
        return target
    existing = _find_existing_comparison(
        config.output_root,
        source_set_id=source_set.source_set_id,
        profile_name=provider.profile.name,
        prompt_id=provider.prompt.prompt_id,
    )
    if existing:
        return existing
    return build_output_path(
        config.output_root,
        source_path=source_set.sources[0].document.path,
        published=source_set.published,
        title=source_set.title,
        profile_name=provider.profile.name,
        prompt_id=provider.prompt.prompt_id,
        identity_suffix=uuid.UUID(source_set.source_set_id).hex[:8],
    )


def _validate_existing_comparison_identity(
    metadata: dict[str, Any],
    *,
    source_set_id: str,
    profile_name: str,
    prompt_id: str,
    target: Path,
    extended_source_set: DocumentSourceSet | None = None,
) -> None:
    if (
        metadata.get("synthesisMode") != "compare"
        or str(metadata.get("summaryProfile") or "") != profile_name
        or str(metadata.get("promptId") or "") != prompt_id
    ):
        raise FileExistsError(
            "refusing to replace an output that belongs to another source set, "
            f"synthesis mode, summary profile, or prompt: {target}"
        )
    if str(metadata.get("sourceSetId") or "") == source_set_id:
        return
    if extended_source_set is None:
        raise FileExistsError(
            "refusing to replace an output that belongs to another source set; "
            f"use --extend-sources with --output and --overwrite to add sources: {target}"
        )
    previous = metadata.get("sources")
    if not isinstance(previous, list) or len(previous) < 2:
        raise ValueError("cannot extend an output without a valid existing source list")
    try:
        old_paths = {
            str(source_reference_to_path(str(entry["source"])).resolve()).casefold()
            for entry in previous
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("cannot extend an output with invalid source references") from exc
    new_paths = {
        str(entry.document.path.resolve()).casefold() for entry in extended_source_set.sources
    }
    if len(old_paths) != len(previous) or not old_paths < new_paths:
        raise FileExistsError(
            "--extend-sources requires every existing source and at least one added source; "
            f"removal, replacement, or reordering alone is not allowed: {target}"
        )


def _is_current_comparison(
    metadata: dict[str, Any],
    *,
    source_set: DocumentSourceSet,
    prompt_version: str,
    prompt_sha256: str,
    profile_sha256: str,
    requested_generator: str | None,
    source_path_format: SourcePathFormat,
    context: str | None = None,
) -> bool:
    generator = str(metadata.get("generator") or "")
    model_matches = requested_generator is None or generator == requested_generator
    sources = metadata.get("sources")
    format_matches = isinstance(sources, list) and all(
        isinstance(entry, dict)
        and source_reference_format(str(entry.get("source") or "")) == source_path_format
        for entry in sources
    )
    return (
        str(metadata.get("title") or "") == source_set.title
        and metadata.get("sourceSetSha256") == source_set.source_set_sha256
        and str(metadata.get("promptVersion") or "") == prompt_version
        and metadata.get("promptSha256") == prompt_sha256
        and metadata.get("summaryProfileSha256") == profile_sha256
        and metadata.get("promptEnvelopeVersion") == COMPARISON_PROMPT_ENVELOPE_VERSION
        and metadata.get("contextSha256") == context_sha256(context)
        and model_matches
        and format_matches
    )


def _comparison_details(
    source_set: DocumentSourceSet,
    provider: ComparisonProvider,
    *,
    dry_run: bool,
    source_path_format: SourcePathFormat,
    generated_title_pending: bool = False,
    context: str | None = None,
) -> dict[str, object]:
    return {
        "validated": not dry_run,
        "synthesis_mode": "compare",
        "source_set_id": source_set.source_set_id,
        "source_set_sha256": source_set.source_set_sha256,
        "source_count": len(source_set.sources),
        "source_paths": [str(entry.document.path) for entry in source_set.sources],
        "source_path_format": source_path_format,
        "context_sha256": context_sha256(context),
        "title": source_set.title,
        "generated_title_pending": generated_title_pending,
        "prompt_id": provider.prompt.prompt_id,
        "prompt_version": provider.prompt.version,
        "prompt_sha256": provider.prompt.sha256,
        "summary_profile": provider.profile.name,
        "summary_profile_sha256": provider.profile.sha256,
        "dry_run": dry_run,
    }


def _synthesize_compare(
    source_values: list[str],
    config: AppConfig,
    *,
    title: str | None,
    provider: ComparisonProvider,
    explicit_output: Path | None,
    overwrite: bool,
    dry_run: bool,
    extend_sources: bool = False,
    context: str | None = None,
) -> SummaryResult:
    source_set = resolve_synthesis_sources(
        source_values,
        mode="compare",
        title=title,
        source_roots=config.source_roots,
        max_input_bytes=config.max_input_bytes,
        max_total_input_bytes=config.max_total_input_bytes,
    )
    _check_total_context(source_set, context, config)
    prompt = provider.prompt
    profile = provider.profile
    automatic_existing = (
        _find_existing_comparison(
            config.output_root,
            source_set_id=source_set.source_set_id,
            profile_name=profile.name,
            prompt_id=prompt.prompt_id,
        )
        if explicit_output is None
        else None
    )
    generated_target_pending = (
        title is None and explicit_output is None and automatic_existing is None
    )
    target = _comparison_target_path(source_set, config, provider, explicit_output)
    if extend_sources and not target.is_file():
        raise ValueError("--extend-sources requires an existing output file")
    target_sha256: str | None = None
    existing_metadata: dict[str, Any] | None = None
    if target.exists() and not generated_target_pending:
        target_sha256 = sha256_bytes(target.read_bytes())
        existing_metadata = _candidate_metadata(target)
        if existing_metadata is None:
            raise FileExistsError(f"existing output is not a readable generated summary: {target}")
        _validate_existing_comparison_identity(
            existing_metadata,
            source_set_id=source_set.source_set_id,
            profile_name=profile.name,
            prompt_id=prompt.prompt_id,
            target=target,
            extended_source_set=source_set if extend_sources else None,
        )
        if title is None:
            stored_title = str(existing_metadata.get("title") or "").strip()
            if not stored_title:
                raise RuntimeError(f"existing comparison has no usable title: {target}")
            source_set = _source_set_with_title(source_set, stored_title)
        existing_errors = validate_summary(target)
        current = _is_current_comparison(
            existing_metadata,
            source_set=source_set,
            prompt_version=prompt.version,
            prompt_sha256=prompt.sha256,
            profile_sha256=profile.sha256,
            requested_generator=_requested_generator(provider, config, comparison=True),
            source_path_format=config.source_path_format,
            context=context,
        )
        if current and not existing_errors and not overwrite:
            logger.info("Comparison note is already current: %s", target)
            return SummaryResult(
                path=target,
                source_path=source_set.sources[0].document.path,
                status="unchanged",
                details=_comparison_details(
                    source_set,
                    provider,
                    dry_run=dry_run,
                    source_path_format=config.source_path_format,
                    context=context,
                ),
            )
        if not overwrite:
            reason = (
                "; ".join(existing_errors)
                if existing_errors
                else "source set, context, comparison profile, or explicitly selected model changed"
            )
            raise FileExistsError(
                f"existing comparison requires explicit --overwrite ({reason}): {target}"
            )
        review_status = str(existing_metadata.get("reviewStatus") or "")
        if review_status in REVIEW_STATUSES and review_status != "unreviewed":
            logger.warning(
                "Overwriting a %s summary resets reviewStatus to unreviewed: %s",
                review_status,
                target,
            )
    request = ComparisonRequest(
        source_set=source_set,
        prompt_envelope_version=COMPARISON_PROMPT_ENVELOPE_VERSION,
        context=context,
    )
    if dry_run:
        action = "updated" if target.exists() else "created"
        logger.info("Dry run: comparison would be %s at %s", action, target)
        details = _comparison_details(
            source_set,
            provider,
            dry_run=True,
            source_path_format=config.source_path_format,
            generated_title_pending=generated_target_pending,
            context=context,
        )
        details["planned_status"] = action
        details["bridge_plan"] = provider.plan(request)
        return SummaryResult(
            path=target,
            source_path=source_set.sources[0].document.path,
            status="planned",
            details=details,
        )
    logger.info("Comparing %d sources", len(source_set.sources))
    generated = provider.generate(request)
    if (
        generated.prompt_id != prompt.prompt_id
        or generated.prompt_version != prompt.version
        or generated.prompt_sha256 != prompt.sha256
        or generated.prompt_envelope_version != COMPARISON_PROMPT_ENVELOPE_VERSION
    ):
        raise RuntimeError(
            "provider returned comparison provenance that does not match the request"
        )
    if title is None:
        source_set = _source_set_with_title(source_set, generated.document.title)
        if generated_target_pending:
            target = _comparison_target_path(source_set, config, provider, explicit_output=None)
            if target.exists():
                raise FileExistsError(
                    "generated title resolves to an existing output that belongs to another "
                    f"comparison: {target}"
                )
    document_errors = validate_comparison_document(
        generated.document,
        source_ids={entry.id for entry in source_set.sources},
        require_all_sources=profile.name == "claims-ja",
    )
    if document_errors:
        raise RuntimeError(
            "generated comparison source validation failed: " + "; ".join(document_errors)
        )
    now = datetime.now().astimezone()
    note_id = (
        str(existing_metadata.get("noteId"))
        if existing_metadata and existing_metadata.get("noteId")
        else None
    )
    created_at = (
        str(existing_metadata.get("created") or existing_metadata.get("date"))
        if existing_metadata and (existing_metadata.get("created") or existing_metadata.get("date"))
        else None
    )
    text = render_comparison_summary(
        source_set=source_set,
        document=generated.document,
        now=now,
        generator=generated.generator,
        profile=profile,
        prompt_envelope_version=COMPARISON_PROMPT_ENVELOPE_VERSION,
        source_path_format=config.source_path_format,
        output_path=target,
        note_id=note_id,
        created_at=created_at,
        context_sha256=context_sha256(context),
    )
    errors = validate_summary_text(text)
    if errors:
        raise RuntimeError("generated comparison validation failed: " + "; ".join(errors))
    if target_sha256 is not None and (
        not target.is_file() or sha256_bytes(target.read_bytes()) != target_sha256
    ):
        raise FileExistsError(
            f"comparison output changed during generation; refusing to replace: {target}"
        )
    status = atomic_write(target, text, overwrite=overwrite)
    persisted_errors = validate_summary(target)
    if persisted_errors:
        raise RuntimeError("persisted comparison validation failed: " + "; ".join(persisted_errors))
    logger.info("Comparison note %s: %s", status, target)
    details = _comparison_details(
        source_set,
        provider,
        dry_run=False,
        source_path_format=config.source_path_format,
        context=context,
    )
    details.update(
        {
            "provider": generated.provider,
            "model": generated.model,
            "provider_version": generated.provider_version,
            "generation_record": generated.generation_record,
            "prompt_envelope_version": COMPARISON_PROMPT_ENVELOPE_VERSION,
            "prompt_source": prompt.source,
            "summary_profile_source": profile.source,
            "output_schema_source": profile.schema.source,
            "output_schema_sha256": profile.schema.sha256,
            "template_id": profile.template.template_id,
            "template_version": profile.template.version,
            "template_source": profile.template.source,
            "template_sha256": profile.template.sha256,
        }
    )
    return SummaryResult(
        path=target,
        source_path=source_set.sources[0].document.path,
        status=status,
        details=details,
    )


def synthesize_compare(
    source_values: list[str],
    config: AppConfig,
    *,
    title: str | None = None,
    explicit_output: Path | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    provider: ComparisonProvider | None = None,
    comparison_profile: str | None = None,
    extend_sources: bool = False,
    context: str | list[str] | None = None,
) -> SummaryResult:
    context = load_context(context, max_input_bytes=config.max_input_bytes)
    started_at = datetime.now().astimezone()
    if extend_sources and (explicit_output is None or not overwrite):
        raise ValueError("--extend-sources requires --output and --overwrite")
    active_provider = provider or comparison_provider_for_config(
        config, comparison_profile=comparison_profile
    )
    try:
        result = _synthesize_compare(
            source_values,
            config,
            title=title,
            provider=active_provider,
            explicit_output=explicit_output,
            overwrite=overwrite,
            dry_run=dry_run,
            extend_sources=extend_sources,
            context=context,
        )
    except Exception as exc:
        if dry_run:
            raise
        report = _write_report(
            config,
            started_at=started_at,
            status="failure",
            error=str(exc),
            provider_error=exc.error_details if isinstance(exc, ProviderExecutionError) else None,
            command="summarize",
        )
        failure = RuntimeError(f"{exc}; report={report}")
        failure.report_path = report  # type: ignore[attr-defined]
        raise failure from exc
    if dry_run:
        return result
    report = _write_report(
        config,
        started_at=started_at,
        status="success",
        result=result,
        command="summarize",
    )
    return result.model_copy(update={"report_path": report})
