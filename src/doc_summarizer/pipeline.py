"""Summary pipeline orchestration."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from doc_summarizer.config import AppConfig
from doc_summarizer.io import atomic_write
from doc_summarizer.models import DocumentSource, SummaryRequest, SummaryResult
from doc_summarizer.naming import build_output_path
from doc_summarizer.notes import (
    REVIEW_STATUSES,
    frontmatter_datetime,
    path_to_file_uri,
    render_summary,
)
from doc_summarizer.prompting import PROMPT_ENVELOPE_VERSION
from doc_summarizer.providers import CodexProvider, SummaryProvider
from doc_summarizer.source import resolve_source, split_frontmatter
from doc_summarizer.validation import validate_summary, validate_summary_text

logger = logging.getLogger(__name__)


def provider_for_config(config: AppConfig) -> SummaryProvider:
    if config.provider != "codex":
        raise ValueError(f"unsupported provider: {config.provider}")
    return CodexProvider(
        executable=config.codex_executable,
        model=config.model,
        timeout_seconds=config.codex_timeout_seconds,
        summary_prompt=config.summary_prompt,
    )


def _candidate_metadata(path: Path) -> dict[str, Any] | None:
    try:
        metadata, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return metadata


def _find_existing(
    output_root: Path,
    *,
    source_uri: str,
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
            metadata.get("source") == source_uri
            and str(metadata.get("promptId") or "") == prompt_id
        ):
            matches.append(candidate)
    if len(matches) > 1:
        raise FileExistsError(
            "multiple summaries share the same source and promptId: "
            + ", ".join(str(path) for path in sorted(matches))
        )
    return matches[0] if matches else None


def _target_path(
    source: DocumentSource,
    config: AppConfig,
    provider: SummaryProvider,
    explicit_output: Path | None,
) -> Path:
    source_uri = path_to_file_uri(source.path)
    if explicit_output is not None:
        target = explicit_output.expanduser()
        target = target if target.is_absolute() else (Path.cwd() / target).resolve()
        if target.suffix.lower() != ".md":
            raise ValueError("--output must use the .md extension")
        return target
    existing = _find_existing(
        config.output_root,
        source_uri=source_uri,
        prompt_id=provider.prompt.prompt_id,
    )
    if existing:
        return existing
    return build_output_path(
        config.output_root,
        source_path=source.path,
        published=source.published,
        title=source.title,
        prompt_id=provider.prompt.prompt_id,
    )


def _validate_existing_identity(
    metadata: dict[str, Any],
    *,
    source_uri: str,
    prompt_id: str,
    target: Path,
) -> None:
    if metadata.get("source") != source_uri or str(metadata.get("promptId") or "") != prompt_id:
        raise FileExistsError(
            f"refusing to replace an output that belongs to another source or prompt: {target}"
        )


def _is_current(
    metadata: dict[str, Any],
    *,
    source: DocumentSource,
    prompt_version: str,
    prompt_sha256: str,
    profile_sha256: str,
    requested_model: str | None,
) -> bool:
    generator = str(metadata.get("generator") or "")
    model_matches = requested_model is None or generator == f"Codex ({requested_model})"
    return (
        metadata.get("sourceSha256") == source.source_sha256
        and str(metadata.get("promptVersion") or "") == prompt_version
        and metadata.get("promptSha256") == prompt_sha256
        and metadata.get("summaryProfileSha256") == profile_sha256
        and metadata.get("promptEnvelopeVersion") == PROMPT_ENVELOPE_VERSION
        and model_matches
    )


def _write_report(
    config: AppConfig,
    *,
    started_at: datetime,
    status: str,
    result: SummaryResult | None = None,
    error: str | None = None,
) -> Path:
    now = datetime.now().astimezone()
    run_id = f"{now.strftime('%Y%m%dT%H%M%S%z')}_{uuid.uuid4().hex[:8]}"
    path = config.reports_root / f"{run_id}.json"
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "command": "summarize",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": now.isoformat(timespec="seconds"),
        "status": status,
        "error": error,
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
) -> SummaryResult:
    source = resolve_source(
        source_value,
        source_roots=config.source_roots,
        max_input_bytes=config.max_input_bytes,
    )
    prompt = provider.prompt
    profile = provider.profile
    target = _target_path(source, config, provider, explicit_output)
    source_uri = path_to_file_uri(source.path)
    existing_metadata: dict[str, Any] | None = None
    if target.exists():
        existing_metadata = _candidate_metadata(target)
        if existing_metadata is None:
            raise FileExistsError(f"existing output is not a readable generated summary: {target}")
        _validate_existing_identity(
            existing_metadata,
            source_uri=source_uri,
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
            requested_model=config.model,
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
                    "dry_run": dry_run,
                },
            )
        if not overwrite:
            reason = (
                "; ".join(existing_errors)
                if existing_errors
                else "source, prompt, or explicitly selected model changed"
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
    if dry_run:
        action = "updated" if target.exists() else "created"
        logger.info("Dry run: summary would be %s at %s", action, target)
        return SummaryResult(
            path=target,
            source_path=source.path,
            status="planned",
            details={
                "planned_status": action,
                "source_sha256": source.source_sha256,
                "prompt_id": prompt.prompt_id,
                "prompt_version": prompt.version,
                "prompt_sha256": prompt.sha256,
                "summary_profile": profile.name,
                "summary_profile_sha256": profile.sha256,
                "dry_run": True,
            },
        )
    request = SummaryRequest(
        source=source,
        prompt_envelope_version=PROMPT_ENVELOPE_VERSION,
    )
    logger.info("Generating structured summary with the configured provider")
    generated = provider.generate(request)
    if (
        generated.prompt_id != prompt.prompt_id
        or generated.prompt_version != prompt.version
        or generated.prompt_sha256 != prompt.sha256
        or generated.prompt_envelope_version != PROMPT_ENVELOPE_VERSION
    ):
        raise RuntimeError("provider returned prompt provenance that does not match the request")
    now = datetime.now().astimezone()
    note_id = (
        str(existing_metadata.get("noteId"))
        if existing_metadata and existing_metadata.get("noteId")
        else None
    )
    created_at = (
        frontmatter_datetime(existing_metadata["date"])
        if existing_metadata and existing_metadata.get("date")
        else None
    )
    text = render_summary(
        source=source,
        document=generated.document,
        now=now,
        generator=generated.generator,
        profile=profile,
        prompt_envelope_version=PROMPT_ENVELOPE_VERSION,
        note_id=note_id,
        created_at=created_at,
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
            "source_sha256": source.source_sha256,
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.version,
            "prompt_sha256": prompt.sha256,
            "prompt_envelope_version": PROMPT_ENVELOPE_VERSION,
            "prompt_source": prompt.source,
            "summary_profile": profile.name,
            "summary_profile_source": profile.source,
            "summary_profile_sha256": profile.sha256,
            "output_schema_source": profile.schema.source,
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
) -> SummaryResult:
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
        )
    except Exception as exc:
        if dry_run:
            raise
        report = _write_report(
            config,
            started_at=started_at,
            status="failure",
            error=str(exc),
        )
        raise RuntimeError(f"{exc}; report={report}") from exc
    if dry_run:
        return result
    report = _write_report(
        config,
        started_at=started_at,
        status="success",
        result=result,
    )
    return result.model_copy(update={"report_path": report})
