"""Deterministic decision policy. Agents contribute signed risk deltas; this module
turns them into a score and an outcome. The LLM never decides, it only explains."""

from __future__ import annotations

from collections.abc import Iterable

from .models import AgentResult

BASE_SCORE = 50
APPROVE_MAX = 35
REFER_MAX = 60
RISK_AGENTS = ("kyc", "credit", "fraud", "compliance")


def classify(score: float) -> str:
    if score <= APPROVE_MAX:
        return "APPROVE"
    if score <= REFER_MAX:
        return "REFER"
    return "DECLINE"


def decide(results: Iterable[AgentResult], exclude: frozenset[str] = frozenset()) -> dict:
    included = [r for r in results if r.agent_id in RISK_AGENTS and r.agent_id not in exclude]
    score = max(0.0, min(100.0, BASE_SCORE + sum(r.risk_delta for r in included)))
    outcome = classify(score)
    stops = [(r.agent_id, r.hard_stop) for r in included if r.hard_stop]
    reasons: list[str] = []
    for agent_id, stop in stops:
        if stop.outcome == "DECLINE":
            outcome = "DECLINE"
            reasons.append(f"{agent_id}: {stop.reason}")
        elif stop.outcome == "REFER" and outcome == "APPROVE":
            outcome = "REFER"
            reasons.append(f"{agent_id}: {stop.reason}")
    return {"score": round(score, 1), "outcome": outcome, "hard_stops": reasons}


def ablation(results: list[AgentResult]) -> list[dict]:
    """For each risk agent, re-run the policy without it: does the decision flip?"""
    full = decide(results)
    rows = []
    for r in results:
        if r.agent_id not in RISK_AGENTS:
            continue
        alt = decide(results, exclude=frozenset({r.agent_id}))
        rows.append(
            {
                "agent_id": r.agent_id,
                "name": r.name,
                "outcome_without": alt["outcome"],
                "score_without": alt["score"],
                "flips": alt["outcome"] != full["outcome"],
            }
        )
    return rows
