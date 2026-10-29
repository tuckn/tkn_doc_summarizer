"""Console interface for document summarization."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, NoReturn

from doc_summarizer import __version__
from doc_summarizer.comparison_resources import (
    load_comparison_profile,
)
from doc_summarizer.config import (
    BUILT_IN_COMPARISON_PROFILES,
    BUILT_IN_SUMMARY_PROFILES,
    DEFAULT_SUMMARY_PROFILE,
    global_config_path,
    initialize_user_config,
    public_config,
    resolve_config,
    user_prompts_root,
)
from doc_summarizer.console_logging import ColorFormatter, log_success, supports_color
from doc_summarizer.output import config_lines as config_lines
from doc_summarizer.output import emit
from doc_summarizer.pipeline import (
    comparison_provider_for_config,
    provider_for_config,
    summarize,
    synthesize_compare,
    synthesize_series,
)
from doc_summarizer.prompting import initialize_user_prompt, load_summary_prompt
from doc_summarizer.source_list import read_source_list
from doc_summarizer.summary_resources import load_summary_profile
from doc_summarizer.validation import validate_summary

logger = logging.getLogger(__name__)


class ArgumentFailure(SystemExit):
    def __init__(self, message: str) -> None:
        super().__init__(2)
        self.message = message


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self._print_message(f"{self.prog}: error: {message}\n", sys.stderr)
        raise ArgumentFailure(message)


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _verbosity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print one JSON result instead of the default key=value list (logs use stderr)",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="suppress progress logs; errors are still shown",
    )
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="show detailed diagnostic logs",
    )


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, help="explicit YAML configuration file")
    parser.add_argument(
        "--source-root",
        dest="source_roots",
        action="append",
        type=Path,
        help="root searched for URL-matching clipped Markdown; repeatable",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--reports-root", type=Path)
    parser.add_argument(
        "--profile", help="application profile in the current mode's generation group"
    )
    parser.add_argument("--bridge-profile", help="shared Bridge profile for this run")
    parser.add_argument("--model", help="Bridge model override for this run")
    parser.add_argument(
        "--provider-timeout-seconds", type=float, help="Bridge timeout for this run"
    )
    parser.add_argument("--max-input-bytes", type=int)
    parser.add_argument("--max-total-input-bytes", type=int)
    parser.add_argument(
        "--summary-profile",
        choices=BUILT_IN_SUMMARY_PROFILES,
        help="built-in summary language/profile override for this run",
    )
    parser.add_argument(
        "--summary-prompt",
        type=Path,
        help="custom summary instructions Markdown file",
    )
    _verbosity(parser)


def _configure_logging(args: argparse.Namespace) -> None:
    level = logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        ColorFormatter(
            "[%(levelname)s] %(message)s",
            use_color=supports_color(sys.stderr),
        )
    )
    logging.basicConfig(level=level, handlers=[handler], force=True)


def _context_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--context",
        action="append",
        metavar="TEXT_OR_FILE",
        help=(
            "supplementary text or UTF-8 file path; repeatable, combined in order; "
            "path-like values must name readable files"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(
        prog="tkn-doc-summarizer",
        description=(
            "Create a Markdown summary or comparison from local documents. URL inputs locate an "
            "already-clipped Markdown file; the CLI does not fetch web pages."
        ),
    )
    _verbosity(parser)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    summary_parser = commands.add_parser(
        "summarize",
        help="generate one summary or comparison note from one or more local sources",
    )
    summary_parser.add_argument(
        "sources",
        nargs="*",
        metavar="SOURCE",
        help="ordered local file paths or clipped URLs; compare requires at least two",
    )
    summary_parser.add_argument(
        "--output",
        type=Path,
        help="exact output .md path; otherwise output_root and automatic naming are used",
    )
    summary_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="regenerate and replace the matching summary, including reviewed edits",
    )
    summary_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve source and target without AI execution or any writes",
    )
    summary_parser.add_argument(
        "--conversation-date",
        help="conversation-ja or meeting-minutes-ja meeting date, YYYY-MM-DD; unknown if omitted",
    )
    _context_options(summary_parser)
    _common(summary_parser)

    summary_parser.add_argument(
        "--sources-file",
        type=Path,
        help="UTF-8 list: one unquoted path/URL per line; relative files use the list directory",
    )
    summary_parser.add_argument(
        "--comparison-profile",
        choices=BUILT_IN_COMPARISON_PROFILES,
        help="compare mode profile; claims-ja organizes attributed claims with source links",
    )
    summary_parser.add_argument(
        "--mode",
        choices=("series", "compare"),
        default="series",
        help=(
            "series summarizes one source or joins ordered sources; "
            "compare analyzes separate sources"
        ),
    )
    summary_parser.add_argument(
        "--title",
        help="title override for multiple sources; otherwise AI derives their combined title",
    )
    summary_parser.add_argument(
        "--extend-sources",
        action="store_true",
        help="compare only: allow added sources for an existing --output; requires --overwrite",
    )

    validate_parser = commands.add_parser("validate", help="validate a generated summary note")
    validate_parser.add_argument("path", type=Path)
    _verbosity(validate_parser)

    config_parser = commands.add_parser("config", help="configuration operations")
    _verbosity(config_parser)
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    config_init = config_commands.add_parser(
        "init",
        help="create the user configuration without overwriting edited settings",
    )
    config_init.add_argument(
        "--force",
        action="store_true",
        help="back up and replace an existing configuration with different content",
    )
    _verbosity(config_init)
    config_list = config_commands.add_parser(
        "list",
        help="list resolved non-secret configuration and value sources as key=value lines",
    )
    _common(config_list)
    config_list.add_argument(
        "--mode",
        choices=("series", "compare"),
        default="series",
        help="generation group targeted by profile and connection overrides (default: series)",
    )
    config_list.add_argument(
        "--comparison-profile",
        choices=BUILT_IN_COMPARISON_PROFILES,
        help="comparison format override; requires --mode compare",
    )

    prompt_parser = commands.add_parser("prompt", help="summary prompt operations")
    _verbosity(prompt_parser)
    prompt_commands = prompt_parser.add_subparsers(dest="prompt_command", required=True)
    prompt_init = prompt_commands.add_parser(
        "init",
        help="create an editable prompt copy with a new UUID",
    )
    prompt_init.add_argument("name", nargs="?", default="summary.md")
    prompt_init.add_argument(
        "--summary-profile",
        choices=BUILT_IN_SUMMARY_PROFILES,
        default=DEFAULT_SUMMARY_PROFILE,
        help="built-in profile whose prompt is copied",
    )
    _verbosity(prompt_init)
    return parser


def _resolved(args: argparse.Namespace) -> Any:
    if getattr(args, "mode", "series") == "compare" and args.summary_prompt is not None:
        raise ValueError("--summary-prompt is not supported with --mode compare")
    overrides = {
        key: getattr(args, key, None)
        for key in (
            "source_roots",
            "output_root",
            "reports_root",
            "profile",
            "bridge_profile",
            "provider_timeout_seconds",
            "model",
            "max_input_bytes",
            "max_total_input_bytes",
            "summary_profile",
            "comparison_profile",
            "summary_prompt",
        )
    }
    return resolve_config(
        explicit_config=getattr(args, "config", None),
        overrides=overrides,
        kind="comparison" if getattr(args, "mode", "series") == "compare" else "summary",
    )


def _failure(args: argparse.Namespace, kind: str, reason: str) -> dict[str, Any]:
    targets = {
        key: str(value) if isinstance(value, Path) else value
        for key in (
            "sources",
            "sources_file",
            "path",
            "output",
            "config",
            "summary_prompt",
            "config_sources",
        )
        if (value := getattr(args, key, None)) is not None
    }
    if (
        getattr(args, "command", None) == "config"
        and getattr(args, "config_command", None) == "init"
    ):
        targets["config"] = str(global_config_path())
    if getattr(args, "command", None) == "prompt":
        targets["prompt"] = str(user_prompts_root() / args.name)
    return {
        "status": "failed",
        "error": reason,
        "error_type": kind,
        "targets": targets,
        "counts": {"failed": 1},
    }


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    tokens = list(sys.argv[1:] if argv is None else argv)
    options = tokens[: tokens.index("--")] if "--" in tokens else tokens
    args = argparse.Namespace(json="--json" in options, quiet=False, verbose=False)
    _configure_logging(args)
    try:
        build_parser().parse_args(tokens, namespace=args)
        if args.quiet and args.verbose:
            raise ArgumentFailure("--quiet and --verbose cannot be combined")
        _configure_logging(args)
        logger.debug("Parsed command: %s", args.command)
        if args.command == "prompt":
            logger.info(
                "Initializing user summary prompt from profile %s: %s",
                args.summary_profile,
                args.name,
            )
            path = initialize_user_prompt(
                args.name,
                profile_name=args.summary_profile,
            )
            prompt = load_summary_prompt(path)
            emit(
                {
                    "status": "created",
                    "path": str(path),
                    "prompt_id": prompt.prompt_id,
                    "prompt_version": prompt.version,
                },
                json_output=args.json,
            )
            return 0
        if args.command == "validate":
            logger.info("Validating summary note: %s", args.path)
            errors = validate_summary(args.path)
            emit(
                {
                    "kind": "summary",
                    "valid": not errors,
                    "errors": errors,
                    "path": str(args.path),
                    "counts": {"checked": 1, "failed": int(bool(errors))},
                },
                json_output=args.json,
            )
            if errors:
                logger.error("Validation failed: %s", args.path)
                return 1
            log_success(logger, "Validation succeeded: %s", args.path)
            return 0
        if args.command == "config" and getattr(args, "config_command", None) == "init":
            init_result = initialize_user_config(force=args.force)
            if init_result.status == "unchanged":
                log_success(
                    logger,
                    "User configuration is already current: %s",
                    init_result.path,
                )
            else:
                log_success(
                    logger,
                    "User configuration %s: %s",
                    init_result.status,
                    init_result.path,
                )
            emit(
                {
                    "status": init_result.status,
                    "path": str(init_result.path),
                    "backup_path": (
                        str(init_result.backup_path) if init_result.backup_path else None
                    ),
                },
                json_output=args.json,
            )
            return 0
        resolved = _resolved(args)
        config = resolved.config
        args.config_sources = resolved.sources[1:]
        logger.debug("Configuration sources: %s", ", ".join(resolved.sources))
        if args.command == "config":
            prompt = load_summary_prompt(
                config.summary_prompt,
                profile_name=config.summary_profile,
            )
            profile = load_summary_profile(config.summary_profile, prompt=prompt)
            comparison_profile = load_comparison_profile(
                profile_name=config.generation.comparison.selected.comparison_profile
            )
            values = public_config(config)
            generation_resolved = {
                "summary": provider_for_config(config).plan()
                | {
                    "default_profile": config.generation.summary.default_profile,
                    "summary_profile": config.summary_profile,
                },
                "comparison": comparison_provider_for_config(config).plan()
                | {
                    "default_profile": config.generation.comparison.default_profile,
                    "comparison_profile": comparison_profile.name,
                },
            }
            values["summary_prompt"] = {
                "configured": values["summary_prompt"],
                "mode": prompt.mode,
                "source": prompt.source,
                "id": prompt.prompt_id,
                "version": prompt.version,
                "sha256": prompt.sha256,
            }
            values["summary_profile"] = {
                "name": profile.name,
                "source": profile.source,
                "sha256": profile.sha256,
                "output_schema": {
                    "id": profile.schema.resource_id,
                    "version": profile.schema.version,
                    "source": profile.schema.source,
                    "sha256": profile.schema.sha256,
                },
                "template": {
                    "source": profile.template.source,
                    "id": profile.template.template_id,
                    "version": profile.template.version,
                    "sha256": profile.template.sha256,
                },
            }
            values["comparison_profile"] = {
                "name": comparison_profile.name,
                "source": comparison_profile.source,
                "sha256": comparison_profile.sha256,
                "prompt": {
                    "source": comparison_profile.prompt.source,
                    "id": comparison_profile.prompt.prompt_id,
                    "version": comparison_profile.prompt.version,
                    "sha256": comparison_profile.prompt.sha256,
                },
                "output_schema": {
                    "source": comparison_profile.schema.source,
                    "sha256": comparison_profile.schema.sha256,
                },
                "template": {
                    "source": comparison_profile.template.source,
                    "id": comparison_profile.template.template_id,
                    "version": comparison_profile.template.version,
                    "sha256": comparison_profile.template.sha256,
                },
            }
            listing_result = {
                "sources": resolved.sources,
                "value_sources": resolved.value_sources,
                "values": values,
                "generationResolved": generation_resolved,
            }
            logger.info("Showing resolved configuration")
            emit(listing_result, json_output=args.json)
            return 0
        if args.command == "summarize":
            if args.conversation_date is not None and args.mode != "series":
                raise ValueError("--conversation-date requires --mode series")
            if args.extend_sources and args.mode != "compare":
                raise ValueError("--extend-sources requires --mode compare")
            if args.sources_file is not None and args.sources:
                raise ValueError("use either SOURCE arguments or --sources-file, not both")
            if args.comparison_profile is not None and args.mode != "compare":
                raise ValueError("--comparison-profile requires --mode compare")
            sources = read_source_list(args.sources_file) if args.sources_file else args.sources
            args.sources = sources
            if not sources:
                raise ValueError("provide at least one SOURCE or --sources-file")
            if args.mode == "compare":
                result = synthesize_compare(
                    sources,
                    config,
                    title=args.title,
                    explicit_output=args.output,
                    overwrite=args.overwrite,
                    dry_run=args.dry_run,
                    comparison_profile=args.comparison_profile,
                    extend_sources=args.extend_sources,
                    context=args.context,
                )
            elif len(sources) == 1:
                if args.title is not None:
                    raise ValueError("--title requires multiple sources")
                result = summarize(
                    sources[0],
                    config,
                    explicit_output=args.output,
                    overwrite=args.overwrite,
                    dry_run=args.dry_run,
                    conversation_date=args.conversation_date,
                    context=args.context,
                )
            else:
                result = synthesize_series(
                    sources,
                    config,
                    title=args.title,
                    explicit_output=args.output,
                    overwrite=args.overwrite,
                    dry_run=args.dry_run,
                    conversation_date=args.conversation_date,
                    context=args.context,
                )
            if result.status == "planned":
                logger.info("Dry run completed without writes")
            elif result.status == "unchanged":
                log_success(logger, "Summary is already current")
            else:
                log_success(logger, "Summary completed successfully")
            payload = result.model_dump(mode="json")
            payload["counts"] = {"sources": len(sources), result.status: 1}
            emit(payload, json_output=args.json)
            return 0
    except ArgumentFailure as exc:
        logger.error("%s", exc.message)
        emit(_failure(args, "argument_error", exc.message), json_output=args.json)
        return 2
    except KeyboardInterrupt:
        logger.error("Interrupted")
        emit(_failure(args, "interrupted", "Interrupted"), json_output=args.json)
        return 130
    except Exception as exc:
        logger.error("%s", exc)
        if getattr(args, "verbose", False):
            logger.debug("Detailed failure", exc_info=True)
        failure = _failure(args, type(exc).__name__, str(exc))
        if isinstance(exc, OSError) and exc.filename:
            failure["path"] = str(exc.filename)
        report_path = getattr(exc, "report_path", None)
        if report_path is not None:
            failure["report_path"] = str(report_path)
        emit(failure, json_output=args.json)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
