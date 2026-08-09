"""Configuration discovery, validation, and precedence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

APP_ID = "doc_summarizer"
DEFAULT_SUMMARY_PROFILE = "default-ja"
BUILT_IN_SUMMARY_PROFILES = ("default-ja", "default-en")


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_roots: list[Path] = Field(default_factory=list)
    output_root: Path
    reports_root: Path
    provider: str = "codex"
    model: str | None = None
    codex_executable: str = "codex"
    codex_timeout_seconds: int = Field(default=1800, ge=1)
    max_input_bytes: int = Field(default=2_000_000, ge=1)
    max_total_input_bytes: int = Field(default=8_000_000, ge=1)
    summary_profile: str = DEFAULT_SUMMARY_PROFILE
    summary_prompt: Path | None = None

    @field_validator("summary_profile")
    @classmethod
    def validate_summary_profile(cls, value: str) -> str:
        if value not in BUILT_IN_SUMMARY_PROFILES:
            allowed = ", ".join(BUILT_IN_SUMMARY_PROFILES)
            raise ValueError(f"summary_profile must be one of: {allowed}")
        return value


class ResolvedConfig(BaseModel):
    config: AppConfig
    sources: list[str]
    value_sources: dict[str, str]


def user_root() -> Path:
    return Path.home() / ".tkn" / APP_ID


def user_prompts_root() -> Path:
    return user_root() / "prompts"


def global_config_path() -> Path:
    return user_root() / "config.yaml"


def default_values() -> dict[str, Any]:
    return {
        "source_roots": [],
        "output_root": user_root() / "data" / "summaries",
        "reports_root": user_root() / "state" / "reports",
        "provider": "codex",
        "model": None,
        "codex_executable": "codex",
        "codex_timeout_seconds": 1800,
        "max_input_bytes": 2_000_000,
        "max_total_input_bytes": 8_000_000,
        "summary_profile": DEFAULT_SUMMARY_PROFILE,
        "summary_prompt": None,
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read config {path}: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return dict(value)


def _resolve_path(value: object, cwd: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (cwd / path).resolve()


def _resolve_paths(values: dict[str, Any], cwd: Path) -> dict[str, Any]:
    result = dict(values)
    roots = result.get("source_roots", [])
    if not isinstance(roots, list):
        raise ValueError("source_roots must be a list")
    result["source_roots"] = [_resolve_path(value, cwd) for value in roots]
    for key in ("output_root", "reports_root"):
        result[key] = _resolve_path(result[key], cwd)
    prompt_value = result.get("summary_prompt")
    if prompt_value is not None:
        raw_prompt = str(prompt_value)
        prompt_path = Path(raw_prompt).expanduser()
        if prompt_path.is_absolute():
            result["summary_prompt"] = prompt_path
        elif Path(raw_prompt).name == raw_prompt:
            result["summary_prompt"] = user_prompts_root() / prompt_path
        else:
            raise ValueError(
                "summary_prompt must be a filename in the user prompts directory "
                "or an absolute path"
            )
    return result


def resolve_config(
    *,
    cwd: Path | None = None,
    explicit_config: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> ResolvedConfig:
    current = (cwd or Path.cwd()).resolve()
    values = default_values()
    sources = ["built-in defaults"]
    value_sources = {key: sources[0] for key in values}
    candidates = [global_config_path(), current / ".tkn" / "config.yaml"]
    if explicit_config is not None:
        explicit = explicit_config.expanduser()
        explicit = explicit if explicit.is_absolute() else (current / explicit).resolve()
        if not explicit.is_file():
            raise ValueError(f"explicit config does not exist: {explicit}")
        candidates.append(explicit)
    for path in candidates:
        if path.is_file():
            loaded = _load_yaml(path)
            values.update(loaded)
            source = str(path)
            sources.append(source)
            value_sources.update({key: source for key in loaded})
    effective_overrides = {
        key: value for key, value in (overrides or {}).items() if value is not None
    }
    if effective_overrides:
        values.update(effective_overrides)
        sources.append("CLI options")
        value_sources.update({key: "CLI options" for key in effective_overrides})
    try:
        config = AppConfig.model_validate(_resolve_paths(values, current))
    except Exception as exc:
        raise ValueError(f"invalid configuration: {exc}") from exc
    return ResolvedConfig(
        config=config,
        sources=sources,
        value_sources=value_sources,
    )


def public_config(config: AppConfig) -> dict[str, object]:
    return {
        "source_roots": [str(path) for path in config.source_roots],
        "output_root": str(config.output_root),
        "reports_root": str(config.reports_root),
        "provider": config.provider,
        "model": config.model,
        "codex_executable": config.codex_executable,
        "codex_timeout_seconds": config.codex_timeout_seconds,
        "max_input_bytes": config.max_input_bytes,
        "max_total_input_bytes": config.max_total_input_bytes,
        "summary_profile": config.summary_profile,
        "summary_prompt": str(config.summary_prompt) if config.summary_prompt else None,
    }
