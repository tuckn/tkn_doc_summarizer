from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def reset_root_logging_after_test() -> Iterator[None]:
    yield
    logging.basicConfig(handlers=[logging.NullHandler()], force=True)
