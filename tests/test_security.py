import time

import pytest
from fastapi.testclient import TestClient

import main
from core.security import RateLimiter, client_ip


@pytest.mark.parametrize("path", ["/", "/healthz", "/api/samples", "/static/app.js"])
def test_security_headers_on_every_response(client, path):
    headers = client.get(path).headers
    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"


def test_api_responses_are_not_cacheable(client):
    assert client.get("/api/samples").headers["cache-control"] == "no-store"


def test_hsts_only_over_https():
    assert "strict-transport-security" not in TestClient(main.app).get("/healthz").headers
    secure = TestClient(main.app, base_url="https://testserver").get("/healthz")
    assert "max-age=" in secure.headers["strict-transport-security"]


def test_hsts_behind_trusted_proxy(monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_TRUST_PROXY", "true")
    response = TestClient(main.app).get("/healthz", headers={"x-forwarded-proto": "https"})
    assert "strict-transport-security" in response.headers


def test_rate_limit_returns_429_with_retry_after(client, body, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_RATE_LIMIT_PER_MIN", "3")
    assert [client.post("/api/underwrite", json=body).status_code for _ in range(3)] == [200, 200, 200]
    blocked = client.post("/api/underwrite", json=body)
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert client.get("/api/samples").status_code == 200  # reads are not limited


def test_rate_limit_applies_to_streaming_endpoint_once_per_request(client, body, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_RATE_LIMIT_PER_MIN", "2")
    for _ in range(2):
        with client.stream("POST", "/api/underwrite/stream", json=body) as response:
            assert response.status_code == 200
            "".join(response.iter_text())
    assert client.post("/api/underwrite/stream", json=body).status_code == 429


def test_rate_limit_can_be_disabled(client, body, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_RATE_LIMIT_PER_MIN", "0")
    assert all(client.post("/api/underwrite", json=body).status_code == 200 for _ in range(30))


def test_spoofed_forwarded_for_cannot_bypass_limit_by_default(client, body, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_RATE_LIMIT_PER_MIN", "1")
    assert client.post("/api/underwrite", json=body, headers={"x-forwarded-for": "1.1.1.1"}).status_code == 200
    assert client.post("/api/underwrite", json=body, headers={"x-forwarded-for": "2.2.2.2"}).status_code == 429


def test_trusted_proxy_separates_clients_by_last_hop(client, body, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_RATE_LIMIT_PER_MIN", "1")
    monkeypatch.setenv("AGENTLEDGER_TRUST_PROXY", "true")
    post = lambda xff: client.post("/api/underwrite", json=body, headers={"x-forwarded-for": xff}).status_code  # noqa: E731
    assert post("evil-spoof, 10.0.0.1") == 200
    assert post("another-spoof, 10.0.0.1") == 429  # same real client; the spoofed first hop is ignored
    assert post("evil-spoof, 10.0.0.2") == 200


def test_client_ip_helper():
    headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
    assert client_ip(headers, "5.5.5.5", trust_proxy=False) == "5.5.5.5"
    assert client_ip(headers, "5.5.5.5", trust_proxy=True) == "10.0.0.1"
    assert client_ip({}, "5.5.5.5", trust_proxy=True) == "5.5.5.5"
    assert client_ip({}, None, trust_proxy=False) == "unknown"


def test_rate_limiter_window_and_memory_bound():
    limiter = RateLimiter(max_keys=5)
    assert limiter.check("a", 2, now=0) is None
    assert limiter.check("a", 2, now=1) is None
    assert limiter.check("a", 2, now=2) == pytest.approx(58)
    assert limiter.check("a", 2, now=61) is None  # the first hit has aged out
    for i in range(50):
        limiter.check(f"client-{i}", 1, now=1000 + i * 100)  # each is stale by the time the next arrives
    assert len(limiter._hits) <= 6
    assert limiter.check("x", 0) is None


def test_oversized_body_is_413(client, body, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_MAX_BODY_BYTES", "200")
    assert client.post("/api/underwrite", json=body).status_code == 413


def test_oversized_chunked_body_without_content_length_is_413(client, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_MAX_BODY_BYTES", "200")
    chunks = iter([b'{"application": "' + b"x" * 150, b"y" * 150 + b'"}'])
    response = client.post("/api/underwrite", content=chunks, headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_server_at_capacity_returns_503(client, body, monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_MAX_CONCURRENT", "1")
    monkeypatch.setattr(main, "_active_runs", 1)
    response = client.post("/api/underwrite", json=body)
    assert response.status_code == 503 and response.headers["retry-after"] == "5"
    monkeypatch.setattr(main, "_active_runs", 0)


def test_server_can_forbid_client_requested_pacing(client, body, monkeypatch):
    body["pacing"] = True
    monkeypatch.setenv("AGENTLEDGER_ALLOW_PACING", "false")
    started = time.perf_counter()
    with client.stream("POST", "/api/underwrite/stream", json=body) as response:
        "".join(response.iter_text())
    assert time.perf_counter() - started < 1.0  # with pacing the run takes at least 1.6 seconds


def test_malformed_environment_values_fall_back_to_safe_defaults(monkeypatch):
    from core.config import get_settings

    monkeypatch.setenv("AGENTLEDGER_RATE_LIMIT_PER_MIN", "lots")
    monkeypatch.setenv("AGENTLEDGER_PIPELINE_TIMEOUT", "soon")
    monkeypatch.setenv("AGENTLEDGER_SERVER_LLM", "definitely")
    settings = get_settings()
    assert settings.rate_limit_per_min == 20 and settings.pipeline_timeout == 45.0
    assert settings.server_llm is False  # anything but an explicit yes/true/on/1 is off
