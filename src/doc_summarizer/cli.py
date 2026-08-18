"""Console interface for document summarization."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from doc_summarizer import __version__
from doc_summarizer.comparison_resources import load_comparison_profile
from doc_summarizer.config import (
    BUILT_IN_SUMMARY_PROFILES,
    DEFAULT_SUMMARY_PROFILE,
    initialize_user_config,
    public_config,
    resolve_config,
)
from doc_summarizer.console_logging import ColorFormatter, log_success, supports_color
from doc_summarizer.pipeline import summarize, synthesize_compare, synthesize_series
from doc_summarizer.prompting import initialize_user_prompt, load_summary_prompt
from doc_summarizer.summary_resources import load_summary_profile
from doc_summarizer.validation import validate_summary

logger = logging.getLogger(__name__)


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _verbosity(parser: argparse.ArgumentParser) -> None:
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress progress logs; errors are still shown",
    )
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
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
    parser.add_argument("--model", help="Codex model override for this run")
    parser.add_argument("--codex-executable")
    parser.add_argument("--codex-timeout-seconds", type=int)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tkn-doc-summarizer",
        description=(
            "Create a Markdown summary from a local document. URL inputs locate an "
            "already-clipped Markdown file; the CLI does not fetch web pages."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    summary_parser = commands.add_parser(
        "summarize",
        help="generate one summary note from a file path or clipped URL",
    )
    summary_parser.add_argument(
        "source",
        help="local file path or URL stored in clipped Frontmatter",
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
        help="resolve source and target without Codex execution or any writes",
    )
    _common(summary_parser)

    synthesize_parser = commands.add_parser(
        "synthesize",
        help="generate one series or comparison note from multiple ordered sources",
    )
    synthesize_parser.add_argument(
        "sources",
        nargs="+",
        metavar="SOURCE",
        help="ordered local file path or URL stored in clipped Frontmatter; requires at least two",
    )
    synthesize_parser.add_argument(
        "--mode",
        choices=("series", "compare"),
        default="series",
        help="series joins consecutive pages; compare analyzes independent sources",
    )
    synthesize_parser.add_argument(
        "--title",
        help="explicit title override; otherwise AI derives it from the complete synthesis",
    )
    synthesize_parser.add_argument(
        "--output",
        type=Path,
        help="exact output .md path; otherwise output_root and automatic naming are used",
    )
    synthesize_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="regenerate and replace the matching synthesis note, including reviewed edits",
    )
    synthesize_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve the ordered sources and target without Codex execution or writes",
    )
    _common(synthesize_parser)

    validate_parser = commands.add_parser("validate", help="validate a generated summary note")
    validate_parser.add_argument("path", type=Path)
    _verbosity(validate_parser)

    config_parser = commands.add_parser("config", help="configuration operations")
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
    config_show = config_commands.add_parser(
        "show",
        help="show resolved non-secret configuration and value sources",
    )
    _common(config_show)

    prompt_parser = commands.add_parser("prompt", help="summary prompt operations")
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
    overrides = {
        key: getattr(args, key, None)
        for key in (
            "source_roots",
            "output_root",
            "reports_root",
            "model",
            "codex_executable",
            "codex_timeout_seconds",
            "max_input_bytes",
            "max_total_input_bytes",
            "summary_profile",
            "summary_prompt",
        )
    }
    return resolve_config(
        explicit_config=getattr(args, "config", None),
        overrides=overrides,
    )


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    args = build_parser().parse_args(argv)
    _configure_logging(args)
    logger.debug("Parsed command: %s", args.command)
    try:
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
            print(
                json.dumps(
                    {
                        "status": "created",
                        "path": str(path),
                        "prompt_id": prompt.prompt_id,
                        "prompt_version": prompt.version,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "validate":
            logger.info("Validating summary note: %s", args.path)
            errors = validate_summary(args.path)
            print(
                json.dumps(
                    {"kind": "summary", "valid": not errors, "errors": errors},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if errors:
                logger.error("Validation failed: %s", args.path)
                return 1
            log_success(logger, "Validation succeeded: %s", args.path)
            return 0
        if args.command == "config" and args.config_command == "init":
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
            print(
                json.dumps(
                    {
                        "status": init_result.status,
                        "path": str(init_result.path),
                        "backup_path": (
                            str(init_result.backup_path) if init_result.backup_path else None
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        resolved = _resolved(args)
        config = resolved.config
        logger.debug("Configuration sources: %s", ", ".join(resolved.sources))
        if args.command == "config":
            prompt = load_summary_prompt(
                config.summary_prompt,
                profile_name=config.summary_profile,
            )
            profile = load_summary_profile(config.summary_profile, prompt=prompt)
            comparison_profile = load_comparison_profile(config.summary_profile)
            values = public_config(config)
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
            print(
                json.dumps(
                    {
                        "sources": resolved.sources,
                        "value_sources": resolved.value_sources,
                        "values": values,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "summarize":
            result = summarize(
                args.source,
                config,
                explicit_output=args.output,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
            if result.status == "planned":
                logger.info("Dry run completed without writes")
            elif result.status == "unchanged":
                log_success(logger, "Summary is already current")
            else:
                log_success(logger, "Summary completed successfully")
            print(
                json.dumps(
                    result.model_dump(mode="json"),
                    ensure_ascii=False,
                    default=_json_default,
                )
            )
            return 0
        if args.command == "synthesize":
            synthesis = synthesize_compare if args.mode == "compare" else synthesize_series
            result = synthesis(
                args.sources,
                config,
                title=args.title,
                explicit_output=args.output,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
            if result.status == "planned":
                logger.info("Dry run completed without writes")
            elif result.status == "unchanged":
                log_success(logger, "%s synthesis is already current", args.mode.capitalize())
            else:
                log_success(logger, "%s synthesis completed successfully", args.mode.capitalize())
            print(
                json.dumps(
                    result.model_dump(mode="json"),
                    ensure_ascii=False,
                    default=_json_default,
                )
            )
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        logger.error("%s", exc)
        if getattr(args, "verbose", False):
            logger.debug("Detailed failure", exc_info=True)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
