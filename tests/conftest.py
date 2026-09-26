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
    import tkn_genai_bridge.config as bridge_config

    import doc_summarizer.config as app_config

    monkeypatch.setattr(app_config, "global_config_path", lambda: tmp_path / "missing-app.yaml")
    monkeypatch.setattr(bridge_config, "user_config_path", lambda: tmp_path / "missing-bridge.yaml")
