from __future__ import annotations

import time

from ..models import AgentResult, Application, Context, Finding, HardStop


class Agent:
    id: str
    name: str
    role: str
    manual_minutes: float  # rough analyst time this step replaces (assumption, for the demo)
    pacing: tuple[float, float] = (0.5, 1.1)  # demo-only delay so the UI can show progress

    async def run(self, app: Application, ctx: Context) -> AgentResult:
        start = time.perf_counter()
        result = await self.analyze(app, ctx)
        result.compute_ms = round((time.perf_counter() - start) * 1000, 2)
        result.manual_minutes = self.manual_minutes
        return result

    async def analyze(self, app: Application, ctx: Context) -> AgentResult:
        raise NotImplementedError

    def result(
        self,
        *,
        summary: str,
        findings: list[Finding],
        confidence: float,
        hard_stop: HardStop | None = None,
        metrics: dict | None = None,
        used_llm: bool = False,
    ) -> AgentResult:
        return AgentResult(
            agent_id=self.id,
            name=self.name,
            role=self.role,
            summary=summary,
            risk_delta=round(sum(f.delta for f in findings), 1),
            confidence=confidence,
            findings=findings,
            hard_stop=hard_stop,
            metrics=metrics or {},
            used_llm=used_llm,
        )
