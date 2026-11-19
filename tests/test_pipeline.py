import asyncio

import pytest
from fastapi.testclient import TestClient

from core.decision import classify
from core.models import Application
from core.orchestrator import AGENTS, run_pipeline
from core.samples import SAMPLES

BY_ID = {s["id"]: s["application"] for s in SAMPLES}


def run(sample_id: str, pacing: bool = False) -> list[dict]:
    async def collect():
        return [e async for e in run_pipeline(Application(**BY_ID[sample_id]), pacing=pacing)]

    return asyncio.run(collect())


def underwriter_metrics(events: list[dict]) -> dict:
    return next(e["result"] for e in events if e["type"] == "agent_done" and e["agent"] == "underwriter")["metrics"]


@pytest.mark.parametrize(
    "sample_id,expected",
    [("clean", "APPROVE"), ("borderline", "REFER"), ("fraud", "DECLINE"), ("sanctions", "DECLINE")],
)
def test_sample_outcomes(sample_id, expected):
    events = run(sample_id)
    assert events[-1]["type"] == "complete"
    assert events[-1]["decision"]["outcome"] == expected


def test_fraud_agent_is_decisive_for_fraud_sample():
    flips = {r["agent_id"]: r for r in underwriter_metrics(run("fraud"))["ablation"]}
    assert flips["fraud"]["flips"] and flips["fraud"]["outcome_without"] == "REFER"
    assert not flips["credit"]["flips"]


def test_compliance_hard_stop_beats_a_low_score():
    events = run("sanctions")
    metrics = underwriter_metrics(events)
    assert classify(metrics["decision"]["score"]) != "DECLINE"  # the score alone would not decline
    assert metrics["decision"]["outcome"] == "DECLINE"
    flips = {r["agent_id"]: r for r in metrics["ablation"]}
    assert flips["compliance"]["flips"] and flips["compliance"]["outcome_without"] == "APPROVE"


def test_contributions_sum_to_score():
    m = underwriter_metrics(run("borderline"))
    total = m["base_score"] + sum(c["delta"] for c in m["contributions"])
    assert m["decision"]["score"] == pytest.approx(min(100, max(0, total)))


def test_stage_two_agents_run_in_parallel_before_underwriter(monkeypatch):
    for agent in AGENTS.values():
        monkeypatch.setattr(agent, "pacing", (0.01, 0.02))
    types = [(e["type"], e.get("agent")) for e in run("clean", pacing=True)]
    idx = types.index
    stage2 = ("credit", "fraud", "compliance")
    assert max(idx(("agent_start", a)) for a in stage2) < min(idx(("agent_done", a)) for a in stage2)
    assert idx(("agent_start", "underwriter")) > max(idx(("agent_done", a)) for a in stage2)
    assert idx(("agent_start", "credit")) > idx(("agent_done", "kyc"))


def test_template_memo_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    m = underwriter_metrics(run("clean"))
    assert m["memo"] and m["llm_error"] is None


def test_api_endpoints():
    from main import app

    client = TestClient(app)
    assert len(client.get("/api/samples").json()) == 4
    assert client.get("/api/graph").json()["stages"][1] == ["credit", "fraud", "compliance"]
    body = {"application": BY_ID["clean"], "pacing": False}
    out = client.post("/api/underwrite", json=body).json()
    assert out["complete"]["decision"]["outcome"] == "APPROVE"
    with client.stream("POST", "/api/underwrite/stream", json=body) as r:
        text = "".join(r.iter_text())
    assert text.count("data: ") >= 10 and '"type": "complete"' in text
    assert client.post("/api/underwrite", json={"application": {**BY_ID["clean"], "age": -1}}).status_code == 422
