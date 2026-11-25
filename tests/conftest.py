import os

import pytest
from fastapi.testclient import TestClient

import main
from core.samples import SAMPLES


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    for name in list(os.environ):
        if name.startswith("AGENTLEDGER_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    main.limiter.reset()
    main._active_runs = 0
    yield
    assert main._active_runs == 0, "a request leaked a concurrency slot"


@pytest.fixture
def client():
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def sample():
    return dict(SAMPLES[0]["application"])


@pytest.fixture
def body(sample):
    return {"application": sample, "pacing": False}
