from __future__ import annotations

import os
from typing import Any

from .. import llm
from ..config import get_settings
from ..decision import BASE_SCORE, RISK_AGENTS, ablation, decide
from ..models import AgentResult, Application, Context, Finding
from .base import Agent

OUTCOME_TEXT = {
    "APPROVE": "Approved",
    "REFER": "Referred to a human underwriter",
    "DECLINE": "Declined",
}


class UnderwriterAgent(Agent):
    id = "underwriter"
    name = "Underwriter Agent"
    role = "Combines agent evidence into a decision and memo"
    manual_minutes = 15
    pacing = (0.6, 1.0)

    async def analyze(self, app: Application, ctx: Context) -> AgentResult:
        specialists = [ctx.results[a] for a in RISK_AGENTS if a in ctx.results]
        decision = decide(specialists)
        flips = ablation(specialists)

        contributions = [
            {"agent_id": r.agent_id, "name": r.name, "delta": r.risk_delta, "confidence": r.confidence} for r in specialists
        ]
        ranked = sorted(
            ((r.name, f) for r in specialists for f in r.findings if f.delta != 0),
            key=lambda x: abs(x[1].delta),
            reverse=True,
        )[:4]
        reasons: list[dict[str, Any]] = [{"agent": n, "label": f.label, "detail": f.detail, "delta": f.delta} for n, f in ranked]
        decisive = [row["name"] for row in flips if row["flips"]]

        credit = ctx.results.get("credit")
        offer = None
        if decision["outcome"] == "APPROVE" and credit:
            offer = {
                "amount": app.loan_amount,
                "term_months": app.term_months,
                "apr": credit.metrics["apr"],
                "monthly_payment": credit.metrics["monthly_payment"],
            }

        template = self._template_memo(app, decision, reasons, decisive)
        memo, used_llm, llm_error = template, False, None
        server_key = os.getenv("ANTHROPIC_API_KEY") if get_settings().server_llm else None
        api_key = ctx.api_key or server_key
        if api_key:
            payload = {
                "applicant": app.applicant_name,
                "decision": decision,
                "agents": [
                    {"name": r.name, "summary": r.summary, "risk_delta": r.risk_delta, "confidence": r.confidence}
                    for r in specialists
                ],
                "top_reasons": reasons,
                "decisive_agents": decisive,
            }
            try:
                memo, used_llm = await llm.write_memo(payload, api_key), True
            except Exception as exc:  # the decision stands even if the memo call fails
                llm_error = type(exc).__name__

        findings = [Finding(f"{r['agent'].replace(' Agent', '')}: {r['label']}", r["detail"], 0, "neutral") for r in reasons]
        return self.result(
            summary=f"{OUTCOME_TEXT[decision['outcome']]} at risk score {decision['score']:g}.",
            findings=findings,
            confidence=round(min(r.confidence for r in specialists), 2),
            used_llm=used_llm,
            metrics={
                "decision": decision,
                "base_score": BASE_SCORE,
                "contributions": contributions,
                "ablation": flips,
                "reasons": reasons,
                "decisive_agents": decisive,
                "offer": offer,
                "memo": memo,
                "llm_error": llm_error,
            },
        )

    @staticmethod
    def _template_memo(app: Application, decision: dict, reasons: list[dict], decisive: list[str]) -> str:
        outcome = decision["outcome"]
        head = (
            f"{OUTCOME_TEXT[outcome]}: {app.applicant_name} scored {decision['score']:g}/100 on the risk scale (lower is safer)."
        )
        if decision["hard_stops"]:
            head += " A hard stop applied: " + "; ".join(decision["hard_stops"]) + "."
        drivers = "; ".join(f'{r["agent"]} flagged "{r["label"].lower()}" ({r["delta"]:+g})' for r in reasons[:3])
        tail = (
            f" The decision depends on {', '.join(decisive)}: without it the outcome would change."
            if decisive
            else " No single agent was decisive; the outcome held when each was removed."
        )
        return f"{head} Biggest drivers: {drivers}.{tail}"
