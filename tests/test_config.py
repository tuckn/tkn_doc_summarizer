from __future__ import annotations

from pathlib import Path

import pytest

import doc_summarizer.config as config_module
from doc_summarizer.config import resolve_config


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
