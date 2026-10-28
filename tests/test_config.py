from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import doc_summarizer.config as config_module
from doc_summarizer.config import (
    config_example_bytes,
    initialize_user_config,
    resolve_config,
)


def test_config_example_is_packaged_and_valid() -> None:
    payload = config_example_bytes()

    assert b"source_roots:" in payload
    assert b"summary_profile: default-ja" in payload
    config = config_module.AppConfig.model_validate({
        **config_module.default_values(), **yaml.safe_load(payload),
    })
    assert config.generation.comparison.profiles["claims"].comparison_profile == "claims-ja"
    assert config.generation.summary.profiles["conversation"].summary_profile == "conversation-ja"


def test_config_init_creates_then_leaves_identical_file_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / ".tkn" / "doc_summarizer" / "config.yaml"
    monkeypatch.setattr(config_module, "global_config_path", lambda: target)

    created = initialize_user_config()
    unchanged = initialize_user_config()

    assert created.status == "created"
    assert created.path == target
    assert unchanged.status == "unchanged"
    assert target.read_bytes() == config_example_bytes()


def test_config_init_protects_edited_file_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("model: custom\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "global_config_path", lambda: target)

    with pytest.raises(FileExistsError, match="refusing to overwrite edited configuration"):
        initialize_user_config()

    assert target.read_text(encoding="utf-8") == "model: custom\n"


def test_config_init_force_backs_up_and_replaces_edited_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("model: custom\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "global_config_path", lambda: target)

    result = initialize_user_config(force=True)

    assert result.status == "replaced"
    assert result.backup_path is not None
    assert result.backup_path.read_text(encoding="utf-8") == "model: custom\n"
    assert target.read_bytes() == config_example_bytes()


def test_five_layer_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_config = tmp_path / "global.yaml"
    global_config.write_text(
        "generation:\n  summary:\n    profiles:\n      default:\n"
        "        overrides:\n          model: global\nmax_input_bytes: 10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "global_config_path", lambda: global_config)
    cwd = tmp_path / "project"
    local = cwd / ".tkn" / "config.yaml"
    local.parent.mkdir(parents=True)
    local.write_text(
        "generation:\n  summary:\n    profiles:\n      default:\n"
        "        overrides:\n          model: local\nmax_input_bytes: 20\n",
        encoding="utf-8",
    )
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text(
        "generation:\n  summary:\n    profiles:\n      default:\n"
        "        overrides:\n          model: explicit\nmax_input_bytes: 30\n",
        encoding="utf-8",
    )

    resolved = resolve_config(
        cwd=cwd,
        explicit_config=explicit,
        overrides={"model": "cli"},
    )

    assert resolved.config.generation.summary.selected.overrides["model"] == "cli"
    assert resolved.config.max_input_bytes == 30
    assert (
        resolved.value_sources["generation.summary.profiles.default.overrides.model"]
        == "CLI options"
    )
    assert resolved.value_sources["max_input_bytes"] == str(explicit)
    assert resolved.config.summary_profile == "default-ja"
    assert resolved.config.max_total_input_bytes == 8_000_000
    assert resolved.config.source_path_format == "native"


def test_source_path_format_can_be_selected_in_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-global.yaml",
    )
    explicit = tmp_path / "config.yaml"
    explicit.write_text("source_path_format: file-uri\n", encoding="utf-8")

    resolved = resolve_config(cwd=tmp_path, explicit_config=explicit)

    assert resolved.config.source_path_format == "file-uri"
    assert resolved.value_sources["source_path_format"] == str(explicit)


def test_unknown_source_path_format_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-global.yaml",
    )

    with pytest.raises(ValueError, match="source_path_format"):
        resolve_config(cwd=tmp_path, overrides={"source_path_format": "unknown"})


def test_unknown_config_key_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-global.yaml",
    )
    explicit = tmp_path / "config.yaml"
    explicit.write_text("unknown: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="extra"):
        resolve_config(cwd=tmp_path, explicit_config=explicit)


def test_missing_explicit_config_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-global.yaml",
    )
    with pytest.raises(ValueError, match="does not exist"):
        resolve_config(cwd=tmp_path, explicit_config=tmp_path / "absent.yaml")


def test_summary_profile_can_be_selected_by_config_or_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-global.yaml",
    )
    explicit = tmp_path / "config.yaml"
    explicit.write_text(
        "generation:\n  summary:\n    profiles:\n      default:\n"
        "        summary_profile: default-en\n", encoding="utf-8",
    )

    configured = resolve_config(cwd=tmp_path, explicit_config=explicit)
    overridden = resolve_config(
        cwd=tmp_path,
        explicit_config=explicit,
        overrides={"summary_profile": "default-ja"},
    )

    assert configured.config.summary_profile == "default-en"
    assert overridden.config.summary_profile == "default-ja"
    assert (
        overridden.value_sources["generation.summary.profiles.default.summary_profile"]
        == "CLI options"
    )


def test_unknown_summary_profile_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-global.yaml",
    )

    with pytest.raises(ValueError, match="summary_profile must be one of"):
        resolve_config(cwd=tmp_path, overrides={"summary_profile": "unknown"})


def test_relative_paths_resolve_from_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "global_config_path",
        lambda: tmp_path / "missing-global.yaml",
    )
    explicit = tmp_path / "config.yaml"
    explicit.write_text(
        "source_roots: [clips]\noutput_root: summaries\nreports_root: reports\n",
        encoding="utf-8",
    )
    resolved = resolve_config(cwd=tmp_path, explicit_config=explicit)
    assert resolved.config.source_roots == [(tmp_path / "clips").resolve()]
    assert resolved.config.output_root == (tmp_path / "summaries").resolve()


def test_nested_profiles_merge_and_cli_targets_selected_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config = tmp_path / "global.yaml"
    global_config.write_text(
        "generation:\n  summary:\n    profiles:\n"
        "      work:\n        bridge_profile: shared-work\n        summary_profile: default-en\n"
        "        overrides:\n          model: base\n          timeout_seconds: 120\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "global_config_path", lambda: global_config)
    local = tmp_path / ".tkn" / "config.yaml"
    local.parent.mkdir()
    local.write_text(
        "generation:\n  summary:\n    default_profile: work\n    profiles:\n"
        "      work:\n        overrides:\n          model: project\n",
        encoding="utf-8",
    )
    resolved = resolve_config(
        cwd=tmp_path,
        overrides={"profile": "work", "model": "cli", "summary_profile": "default-ja"},
    )
    selected = resolved.config.generation.summary.selected
    assert selected.bridge_profile == "shared-work"
    assert selected.overrides == {"model": "cli", "timeout_seconds": 120}
    assert resolved.config.summary_profile == "default-ja"
    assert resolved.config.generation.summary.profiles["default"].overrides == {}
    assert resolved.config.generation.comparison.selected.overrides == {}
    assert resolved.sources.count("CLI options") == 1
    prefix = "generation.summary.profiles.work"
    assert resolved.value_sources[f"{prefix}.bridge_profile"] == str(global_config)
    assert resolved.value_sources[f"{prefix}.overrides.timeout_seconds"] == str(global_config)
    assert resolved.value_sources[f"{prefix}.overrides.model"] == "CLI options"


def test_null_model_overrides_lower_layer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    global_config = tmp_path / "global.yaml"
    global_config.write_text(
        "generation:\n  summary:\n    profiles:\n      default:\n"
        "        overrides:\n          model: lower\n          timeout_seconds: 60\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "global_config_path", lambda: global_config)
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text(
        "generation:\n  summary:\n    profiles:\n      default:\n"
        "        overrides:\n          model: null\n", encoding="utf-8",
    )
    config = resolve_config(cwd=tmp_path, explicit_config=explicit).config
    assert config.generation.summary.selected.overrides == {"model": None, "timeout_seconds": 60}


@pytest.mark.parametrize(
    "text,match",
    [
        ("model: old\ngeneration: {}\n", "extra"),
        ("generation:\n  active_profile: missing\n", "extra"),
        ("schema_version: '9.0.0'\n", "schema_version"),
        (
            "generation:\n  summary:\n    profiles:\n      default:\n"
            "        bridge_profile: ' '", "blank",
        ),
        ("generation:\n  summary:\n    default_profile: missing\n", "default_profile"),
        ("generation:\n  comparison:\n    default_profile: missing\n", "default_profile"),
        ("generation:\n  summary:\n    profiles: null\n", "profiles"),
        ("generation:\n  comparison: null\n", "comparison"),
        (
            "generation:\n  comparison:\n    profiles:\n      default:\n"
            "        comparison_profile: default-ja\n", "comparison_profile",
        ),
        (
            "generation:\n  summary:\n    profiles:\n      default:\n"
            "        comparison_profile: compare-ja\n", "extra",
        ),
        (
            "generation:\n  comparison:\n    profiles:\n      default:\n"
            "        summary_profile: default-ja\n", "extra",
        ),
        ("generation:\n  summary:\n    default_profile: ' '\n", "blank"),
        ("generation:\n  comparison:\n    profiles:\n      ' ': {}\n", "blank"),
    ],
)
def test_invalid_generation_config_is_rejected(tmp_path: Path, text: str, match: str) -> None:
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        resolve_config(cwd=tmp_path, explicit_config=explicit)


@pytest.mark.parametrize(
    "text",
    [
        "schema_version: '1.0.0'\n",
        "generation:\n  summary_profile: default-ja\n",
        "generation:\n  profiles:\n    codex:\n      bridge_profile: codex-default\n",
        *[f"{key}: codex\n" for key in (
            "model", "provider", "codex_executable", "codex_timeout_seconds",
            "summary_profile", "bridge_profile", "provider_timeout_seconds",
        )],
    ],
)
def test_legacy_settings_are_rejected(tmp_path: Path, text: str) -> None:
    explicit = tmp_path / "old.yaml"
    explicit.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid configuration"):
        resolve_config(cwd=tmp_path, explicit_config=explicit)


@pytest.mark.parametrize("kind", ["summary", "comparison"])
def test_cli_overrides_only_selected_mode(tmp_path: Path, kind: str) -> None:
    explicit = tmp_path / "config.yaml"
    explicit.write_text(yaml.safe_dump({
        "generation": {
            group: {
                "default_profile": "work",
                "profiles": {"work": {
                    "bridge_profile": f"{group}-bridge",
                    f"{group}_profile": (
                        "conversation-ja" if group == "summary" else "claims-ja"
                    ),
                    "overrides": {"model": group, "timeout_seconds": 60},
                }, "alternate": {"bridge_profile": "alternate"}},
            } for group in ("summary", "comparison")
        },
    }), encoding="utf-8")
    resolved = resolve_config(
        cwd=tmp_path, explicit_config=explicit, kind=kind,
        overrides={
            "profile": "alternate", "bridge_profile": "cli-bridge",
            "model": "cli-model", "provider_timeout_seconds": 120,
            f"{kind}_profile": "default-en" if kind == "summary" else "compare-en",
        },
    )
    section = getattr(resolved.config.generation, kind)
    other = getattr(
        resolved.config.generation, "comparison" if kind == "summary" else "summary",
    )
    assert section.default_profile == "alternate"
    assert section.selected.bridge_profile == "cli-bridge"
    assert section.selected.overrides == {"model": "cli-model", "timeout_seconds": 120}
    assert getattr(section.selected, f"{kind}_profile").endswith("-en")
    assert other.default_profile == "work"
    assert other.selected.bridge_profile.endswith("-bridge")
    assert other.selected.overrides["timeout_seconds"] == 60
    prefix = f"generation.{kind}.profiles.alternate"
    assert resolved.value_sources[f"{prefix}.bridge_profile"] == "CLI options"


@pytest.mark.parametrize(
    "kind,overrides,match",
    [
        ("summary", {"profile": "absent"}, "default_profile"),
        ("comparison", {"profile": "absent"}, "default_profile"),
        ("summary", {"comparison_profile": "claims-ja"}, "--mode compare"),
        ("comparison", {"summary_profile": "default-en"}, "--mode series"),
    ],
)
def test_mode_overrides_reject_invalid_selection(
    tmp_path: Path, kind: str, overrides: dict[str, str], match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        resolve_config(cwd=tmp_path, kind=kind, overrides=overrides)


def test_bridge_profile_defaults_to_shared_selection(tmp_path: Path) -> None:
    config = resolve_config(cwd=tmp_path).config
    assert config.generation.summary.selected.bridge_profile is None
    assert config.generation.comparison.selected.bridge_profile is None


@pytest.mark.parametrize("kind", ["summary", "comparison"])
def test_null_bridge_profile_clears_lower_explicit_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    global_config = tmp_path / "global.yaml"
    global_config.write_text(yaml.safe_dump({"generation": {
        kind: {"profiles": {"default": {"bridge_profile": "pinned"}}},
    }}), encoding="utf-8")
    monkeypatch.setattr(config_module, "global_config_path", lambda: global_config)
    explicit = tmp_path / "config.yaml"
    explicit.write_text(yaml.safe_dump({"generation": {
        kind: {"profiles": {"default": {"bridge_profile": None}}},
    }}), encoding="utf-8")
    resolved = resolve_config(cwd=tmp_path, explicit_config=explicit)
    assert getattr(resolved.config.generation, kind).selected.bridge_profile is None
    assert (
        resolved.value_sources[f"generation.{kind}.profiles.default.bridge_profile"]
        == str(explicit)
    )
