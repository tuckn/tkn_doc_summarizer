from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def reset_root_logging_after_test() -> Iterator[None]:
    yield
    logging.basicConfig(handlers=[logging.NullHandler()], force=True)


@pytest.fixture(autouse=True)
def isolate_user_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tkn_genai_bridge
    import tkn_genai_bridge.config as bridge_config

    import doc_summarizer.config as app_config

    monkeypatch.setattr(app_config, "global_config_path", lambda: tmp_path / "missing-app.yaml")
    broken = tmp_path / "broken-bridge.yaml"
    broken.write_text("broken: [", encoding="utf-8")
    monkeypatch.setattr(bridge_config, "user_config_path", lambda: broken)

    def bridge_config_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("GenAI Bridge configuration files must never be read")

    # Connections come only from this application's genai_profiles.
    for module in (bridge_config, tkn_genai_bridge):
        monkeypatch.setattr(module, "load_config", bridge_config_read)
        monkeypatch.setattr(module, "load_profile", bridge_config_read)
