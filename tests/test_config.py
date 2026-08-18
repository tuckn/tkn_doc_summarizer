from __future__ import annotations

from pathlib import Path

import pytest

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
        "model: global\nmax_input_bytes: 10\nsummary_profile: default-ja\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "global_config_path", lambda: global_config)
    cwd = tmp_path / "project"
    local = cwd / ".tkn" / "config.yaml"
    local.parent.mkdir(parents=True)
    local.write_text("model: local\nmax_input_bytes: 20\n", encoding="utf-8")
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("model: explicit\nmax_input_bytes: 30\n", encoding="utf-8")

    resolved = resolve_config(
        cwd=cwd,
        explicit_config=explicit,
        overrides={"model": "cli"},
    )

    assert resolved.config.model == "cli"
    assert resolved.config.max_input_bytes == 30
    assert resolved.value_sources["model"] == "CLI options"
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
    explicit.write_text("summary_profile: default-en\n", encoding="utf-8")

    configured = resolve_config(cwd=tmp_path, explicit_config=explicit)
    overridden = resolve_config(
        cwd=tmp_path,
        explicit_config=explicit,
        overrides={"summary_profile": "default-ja"},
    )

    assert configured.config.summary_profile == "default-en"
    assert overridden.config.summary_profile == "default-ja"
    assert overridden.value_sources["summary_profile"] == "CLI options"


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
