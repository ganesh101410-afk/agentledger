import asyncio

import pytest

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


@pytest.mark.parametrize("sample_id", list(BY_ID))
def test_contributions_always_add_up_to_the_score(sample_id):
    m = underwriter_metrics(run(sample_id))
    total = m["base_score"] + sum(c["delta"] for c in m["contributions"])
    assert m["decision"]["score"] == pytest.approx(min(100, max(0, total)))


def test_pipeline_timeout_emits_one_error_and_no_decision(monkeypatch):
    monkeypatch.setenv("AGENTLEDGER_PIPELINE_TIMEOUT", "0.05")
    for agent in AGENTS.values():
        monkeypatch.setattr(agent, "pacing", (5, 5))
    events = run("clean", pacing=True)
    assert [e["type"] for e in events if e["type"] in ("error", "complete")] == ["error"]
    assert "timed out" in events[-1]["message"]


def test_agent_crash_gives_a_generic_error_without_internals(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("secret internals /etc/passwd")

    monkeypatch.setattr(AGENTS["credit"], "analyze", boom)
    events = run("clean")
    error = next(e for e in events if e["type"] == "error")
    assert "secret" not in error["message"] and "failed" in error["message"]
    assert not any(e["type"] == "complete" for e in events)


def test_closing_the_stream_early_cancels_the_background_work(monkeypatch):
    for agent in AGENTS.values():
        monkeypatch.setattr(agent, "pacing", (5, 5))

    async def scenario():
        stream = run_pipeline(Application(**BY_ID["clean"]), pacing=True)
        await anext(stream)  # first event arrives, agents are now sleeping
        await stream.aclose()  # what happens when the browser disconnects
        await asyncio.sleep(0.05)
        return [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    assert asyncio.run(scenario()) == []
