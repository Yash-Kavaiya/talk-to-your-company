import os

import pytest

# Tests always run in mock mode, whatever the shell has set.
for _var in ("PERCEPTION", "LLM", "ASR", "TTS"):
    os.environ[_var] = "mock"

from app.config import Settings, Site, load_site  # noqa: E402
from app.events.store import EventStore  # noqa: E402


@pytest.fixture
def site() -> Site:
    return load_site()


@pytest.fixture
def store() -> EventStore:
    return EventStore()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path)
