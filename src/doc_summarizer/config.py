"""Configuration discovery, validation, and precedence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from doc_summarizer.io import atomic_write

APP_ID = "doc_summarizer"
DEFAULT_SUMMARY_PROFILE = "default-ja"
BUILT_IN_SUMMARY_PROFILES = ("default-ja", "default-en")
SourcePathFormat = Literal["native", "file-uri"]


def _merge(base: dict[str, Any], layer: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in layer.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _normalize_layer(layer: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Translate old flat AI settings before merging, preserving layer priority."""
    result = deepcopy(layer)
    legacy_keys = {
        "summary_profile",
        "bridge_profile",
        "model",
        "provider_timeout_seconds",
        "codex_timeout_seconds",
        "provider",
        "codex_executable",
    }
    legacy = {key: result.pop(key) for key in legacy_keys if key in result}
    if not legacy:
        return result
    if "generation" in result:
        raise ValueError("do not mix generation with legacy top-level AI settings in one config")
    generation: dict[str, Any] = {}
    if "summary_profile" in legacy:
        generation["summary_profile"] = legacy["summary_profile"]
    connection: dict[str, Any] = {}
    if "bridge_profile" in legacy:
        connection["bridge_profile"] = legacy["bridge_profile"]
    if legacy.get("provider") is not None:
        connection["legacy_provider"] = legacy["provider"]
    overrides: dict[str, Any] = {}
    for old, new in (
        ("model", "model"),
        ("codex_timeout_seconds", "timeout_seconds"),
        ("provider_timeout_seconds", "timeout_seconds"),
    ):
        if old in legacy and legacy[old] is not None:
            overrides[new] = legacy[old]
    if legacy.get("codex_executable") is not None:
        overrides["cli"] = {"executable": legacy["codex_executable"]}
        connection.setdefault("legacy_provider", "codex")
    if overrides:
        connection["overrides"] = overrides
    if connection:
        active, previous = _selected_values(base, allow_missing=True)
        if "bridge_profile" not in previous:
            connection.setdefault("bridge_profile", "codex-default")
        generation["profiles"] = {active: connection}
    result["generation"] = generation
    return result


def _selected_values(
    values: dict[str, Any],
    *,
    allow_missing: bool = False,
) -> tuple[str, dict[str, Any]]:
    generation = values.get("generation", {})
    if not isinstance(generation, dict):
        raise ValueError("generation must be a mapping")
    active = generation.get("active_profile", "codex")
    profiles = generation.get("profiles", {})
    if not isinstance(active, str) or not isinstance(profiles, dict):
        raise ValueError("generation requires an active_profile name and profiles mapping")
    if active not in profiles and not allow_missing:
        raise ValueError("generation.active_profile must name an entry in generation.profiles")
    selected = profiles.get(active, {})
    if not isinstance(selected, dict) or not isinstance(selected.get("overrides", {}), dict):
        raise ValueError("generation profile and overrides must be mappings")
    return active, selected


class GenerationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_profile: str = Field(min_length=1)
    overrides: dict[str, Any] = Field(default_factory=dict)
    # Only populated by the legacy reader; keep the old Codex-only restriction.
    legacy_provider: str | None = None

    @field_validator("bridge_profile")
    @classmethod
    def validate_bridge_profile(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bridge_profile must not be blank")
        return value


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_profile: str = DEFAULT_SUMMARY_PROFILE
    active_profile: str = Field(default="codex", min_length=1)
    profiles: dict[str, GenerationProfile] = Field(
        default_factory=lambda: {"codex": GenerationProfile(bridge_profile="codex-default")}
    )

    @field_validator("summary_profile")
    @classmethod
    def validate_summary_profile(cls, value: str) -> str:
        if value not in BUILT_IN_SUMMARY_PROFILES:
            allowed = ", ".join(BUILT_IN_SUMMARY_PROFILES)
            raise ValueError(f"summary_profile must be one of: {allowed}")
        return value

    @model_validator(mode="after")
    def validate_active_profile(self) -> Self:
        if any(not name.strip() for name in self.profiles):
            raise ValueError("generation profile names must not be blank")
        if self.active_profile not in self.profiles:
            raise ValueError("generation.active_profile must name an entry in generation.profiles")
        return self

    @property
    def selected(self) -> GenerationProfile:
        return self.profiles[self.active_profile]


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_roots: list[Path] = Field(default_factory=list)
    output_root: Path
    reports_root: Path
    schema_version: Literal["1.0.0"] = "1.0.0"
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    max_input_bytes: int = Field(default=2_000_000, ge=1)
    max_total_input_bytes: int = Field(default=8_000_000, ge=1)
    source_path_format: SourcePathFormat = "native"
    summary_prompt: Path | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy(cls, value: Any) -> Any:
        return _normalize_layer(value, {}) if isinstance(value, dict) else value

    @property
    def summary_profile(self) -> str:
        return self.generation.summary_profile

    @property
    def model(self) -> str | None:
        value = self.generation.selected.overrides.get("model")
        return value if isinstance(value, str) else None


class ResolvedConfig(BaseModel):
    config: AppConfig
    sources: list[str]
    value_sources: dict[str, str]


@dataclass(frozen=True)
class ConfigInitResult:
    status: str
    path: Path
    backup_path: Path | None = None


def user_root() -> Path:
    return Path.home() / ".tkn" / APP_ID


def user_prompts_root() -> Path:
    return user_root() / "prompts"


def global_config_path() -> Path:
    return user_root() / "config.yaml"


def config_example_bytes() -> bytes:
    resource_name = "resources/config.example.yaml"
    resource = files("doc_summarizer").joinpath(resource_name)
    try:
        return resource.read_bytes()
    except (OSError, FileNotFoundError) as exc:
        raise RuntimeError(
            f"built-in configuration example is unavailable: {resource_name}: {exc}"
        ) from exc


def initialize_user_config(*, force: bool = False) -> ConfigInitResult:
    path = global_config_path()
    payload = config_example_bytes()
    if not path.exists():
        status = atomic_write(path, payload)
        return ConfigInitResult(status=status, path=path)
    if path.read_bytes() == payload:
        return ConfigInitResult(status="unchanged", path=path)
    if not force:
        raise FileExistsError(
            f"refusing to overwrite edited configuration: {path}; "
            "re-run with --force to create a backup and replace it"
        )
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    atomic_write(backup_path, path.read_bytes())
    status = atomic_write(path, payload, overwrite=True)
    return ConfigInitResult(
        status="replaced" if status == "updated" else status,
        path=path,
        backup_path=backup_path,
    )


def default_values() -> dict[str, Any]:
    return {
        "source_roots": [],
        "output_root": user_root() / "data" / "summaries",
        "reports_root": user_root() / "state" / "reports",
        "schema_version": "1.0.0",
        "generation": GenerationConfig().model_dump(),
        "max_input_bytes": 2_000_000,
        "max_total_input_bytes": 8_000_000,
        "source_path_format": "native",
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
    value_sources = {key: sources[0] for key in _leaves(values)}
    candidates = [global_config_path(), current / ".tkn" / "config.yaml"]
    if explicit_config is not None:
        explicit = explicit_config.expanduser()
        explicit = explicit if explicit.is_absolute() else (current / explicit).resolve()
        if not explicit.is_file():
            raise ValueError(f"explicit config does not exist: {explicit}")
        candidates.append(explicit)

    def merge_layer(layer: dict[str, Any], source: str) -> None:
        nonlocal values
        normalized = _normalize_layer(layer, values)
        if "generation" not in layer:
            for old, new in (
                ("model", "model"),
                ("codex_timeout_seconds", "timeout_seconds"),
                ("provider_timeout_seconds", "timeout_seconds"),
            ):
                if old in layer and layer[old] is None:
                    _, selected = _selected_values(values, allow_missing=True)
                    selected.get("overrides", {}).pop(new, None)
        values = _merge(values, normalized)
        if source not in sources:
            sources.append(source)
        value_sources.update({key: source for key in layer})
        value_sources.update({key: source for key in _leaves(normalized)})

    for path in candidates:
        if path.is_file():
            merge_layer(_load_yaml(path), str(path))
    effective_overrides = {
        key: value for key, value in (overrides or {}).items() if value is not None
    }
    if effective_overrides:
        if "profile" in effective_overrides:
            merge_layer(
                {"generation": {"active_profile": effective_overrides.pop("profile")}},
                "CLI options",
            )
        _selected_values(values)
        merge_layer(effective_overrides, "CLI options")
    try:
        config = AppConfig.model_validate(_resolve_paths(values, current))
    except Exception as exc:
        raise ValueError(f"invalid configuration: {exc}") from exc
    return ResolvedConfig(
        config=config,
        sources=sources,
        value_sources=value_sources,
    )


def _leaves(values: dict[str, Any], prefix: str = "") -> list[str]:
    result: list[str] = []
    for key, value in values.items():
        name = f"{prefix}.{key}" if prefix else key
        result.extend(_leaves(value, name) if isinstance(value, dict) and value else [name])
    return result


def public_config(config: AppConfig) -> dict[str, Any]:
    return config.model_dump(mode="json")
