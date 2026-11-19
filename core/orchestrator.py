"""Staged agent graph: KYC first, then credit / fraud / compliance in parallel, then the underwriter."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator

from .agents.compliance import ComplianceAgent
from .agents.credit import CreditRiskAgent
from .agents.fraud import FraudAgent
from .agents.kyc import KYCAgent
from .agents.underwriter import UnderwriterAgent
from .models import Application, Context

AGENTS = {a.id: a for a in (KYCAgent(), CreditRiskAgent(), FraudAgent(), ComplianceAgent(), UnderwriterAgent())}
STAGES = [["kyc"], ["credit", "fraud", "compliance"], ["underwriter"]]


def graph_spec() -> dict:
    return {
        "stages": STAGES,
        "agents": [{"id": a.id, "name": a.name, "role": a.role, "manual_minutes": a.manual_minutes} for a in AGENTS.values()],
    }


async def run_pipeline(app: Application, api_key: str | None = None, pacing: bool = True) -> AsyncIterator[dict]:
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    ctx = Context(api_key=api_key)
    started = time.perf_counter()

    async def run_agent(agent_id: str) -> None:
        agent = AGENTS[agent_id]
        await queue.put({"type": "agent_start", "agent": agent_id})
        if pacing:  # purely visual, excluded from each agent's compute_ms
            await asyncio.sleep(random.uniform(*agent.pacing))
        result = await agent.run(app, ctx)
        ctx.results[agent_id] = result
        await queue.put({"type": "agent_done", "agent": agent_id, "result": result.to_dict()})

    async def driver() -> None:
        try:
            for index, stage in enumerate(STAGES):
                await queue.put({"type": "stage_start", "stage": index, "agents": stage})
                await asyncio.gather(*(run_agent(a) for a in stage))
            final = ctx.results["underwriter"]
            await queue.put(
                {
                    "type": "complete",
                    "decision": final.metrics["decision"],
                    "wall_ms": round((time.perf_counter() - started) * 1000),
                    "compute_ms_total": round(sum(r.compute_ms for r in ctx.results.values()), 1),
                    "manual_minutes_total": sum(r.manual_minutes for r in ctx.results.values()),
                }
            )
        except Exception as exc:
            await queue.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(driver())
    try:
        while (event := await queue.get()) is not None:
            yield event
    finally:
        task.cancel()
