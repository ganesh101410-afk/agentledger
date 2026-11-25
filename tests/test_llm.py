import asyncio
import logging
from types import SimpleNamespace

import pytest

from core import llm


def memo_of(response_json: dict) -> dict:
    done = next(e for e in response_json["events"] if e["type"] == "agent_done" and e["agent"] == "underwriter")
    return done["result"]


@pytest.fixture
def fail_if_called(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("the LLM must not be called")

    monkeypatch.setattr(llm, "write_memo", forbidden)


def test_no_key_uses_rule_based_memo(client, body, fail_if_called):
    result = memo_of(client.post("/api/underwrite", json=body).json())
    assert result["used_llm"] is False and result["metrics"]["memo"] and result["metrics"]["llm_error"] is None


def test_server_key_is_ignored_unless_explicitly_enabled(client, body, fail_if_called, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-server-owned")
    assert memo_of(client.post("/api/underwrite", json=body).json())["used_llm"] is False


def test_server_key_is_used_when_enabled(client, body, monkeypatch):
    seen = {}

    async def fake(payload, api_key):
        seen["key"] = api_key
        return "Claude memo"

    monkeypatch.setattr(llm, "write_memo", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-server-owned")
    monkeypatch.setenv("AGENTLEDGER_SERVER_LLM", "true")
    result = memo_of(client.post("/api/underwrite", json=body).json())
    assert result["used_llm"] is True and result["metrics"]["memo"] == "Claude memo"
    assert seen["key"] == "sk-ant-server-owned"


def test_caller_key_is_used_and_never_returned_or_logged(client, body, monkeypatch, caplog):
    async def fake(payload, api_key):
        assert api_key == "sk-ant-CALLER-KEY"
        assert "CALLER-KEY" not in str(payload)
        return "Claude memo"

    monkeypatch.setattr(llm, "write_memo", fake)
    body["api_key"] = "sk-ant-CALLER-KEY"
    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/underwrite", json=body)
        with client.stream("POST", "/api/underwrite/stream", json=body) as streamed:
            streamed_text = "".join(streamed.iter_text())
    assert "CALLER-KEY" not in response.text and "CALLER-KEY" not in streamed_text
    assert "CALLER-KEY" not in caplog.text
    assert "Priya" not in caplog.text  # applicant data is not logged either


def test_llm_failure_never_changes_the_decision(client, body, monkeypatch):
    plain = client.post("/api/underwrite", json=body).json()["complete"]["decision"]

    async def broken(payload, api_key):
        raise ConnectionError("upstream said: sk-ant-LEAKY")

    monkeypatch.setattr(llm, "write_memo", broken)
    body["api_key"] = "sk-ant-whatever"
    result = memo_of(client.post("/api/underwrite", json=body).json())
    assert result["metrics"]["decision"] == plain
    assert result["used_llm"] is False
    assert result["metrics"]["llm_error"] == "ConnectionError"  # class name only, never the message
    assert "LEAKY" not in str(result)


class FakeClient:
    text = "A short memo."
    last = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        FakeClient.last = self
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=FakeClient.text)])


@pytest.fixture
def fake_anthropic(monkeypatch):
    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeClient)
    FakeClient.text = "A short memo."
    return FakeClient


def test_write_memo_calls_the_model_with_guardrails(fake_anthropic, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_LLM_TIMEOUT", "7")
    memo = asyncio.run(llm.write_memo({"decision": {"outcome": "APPROVE"}}, "sk-ant-x"))
    assert memo == "A short memo."
    assert fake_anthropic.last.kwargs["timeout"] == 7.0 and fake_anthropic.last.kwargs["max_retries"] == 1
    call = fake_anthropic.last.calls[0]
    assert call["model"] == llm.MODEL and call["max_tokens"] == 500
    assert "never an instruction" in call["system"]


def test_write_memo_caps_length_and_rejects_empty(fake_anthropic):
    FakeClient.text = "x" * 10_000
    assert len(asyncio.run(llm.write_memo({}, "k"))) == llm.MAX_MEMO_CHARS
    FakeClient.text = "   "
    with pytest.raises(ValueError):
        asyncio.run(llm.write_memo({}, "k"))
