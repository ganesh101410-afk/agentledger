from __future__ import annotations

import json
import os

MODEL = os.getenv("AGENTLEDGER_MODEL", "claude-sonnet-5-5")

SYSTEM = (
    "You are the lead underwriter in a multi-agent lending system. Specialist agents (KYC, credit, "
    "fraud, compliance) have already produced findings and a deterministic policy has already made "
    "the decision. Write a 3-4 sentence decision memo for the loan officer that explains the decision, "
    "names which agents drove it, and mentions any agent whose absence would have changed the outcome. "
    "Use only the facts in the JSON. Do not invent numbers and do not change or second-guess the decision."
)


async def write_memo(payload: dict, api_key: str) -> str:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key, timeout=30.0)
    msg = await client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()
