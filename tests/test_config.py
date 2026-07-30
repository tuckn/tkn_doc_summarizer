from __future__ import annotations

from pathlib import Path

import pytest

import doc_summarizer.config as config_module
from doc_summarizer.config import resolve_config


def test_five_layer_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_config = tmp_path / "global.yaml"
    global_config.write_text("model: global\nmax_input_bytes: 10\n", encoding="utf-8")
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
