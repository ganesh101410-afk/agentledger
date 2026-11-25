"""Runtime settings, read from the environment on every call so tests and operators can change them."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    allow_pacing: bool  # honour the demo pacing delay requested by the client
    server_llm: bool  # let the server's own ANTHROPIC_API_KEY pay for memos (off: only caller-supplied keys)
    max_concurrent: int  # simultaneous pipeline runs before answering 503
    rate_limit_per_min: int  # POSTs per client per minute before answering 429 (0 disables)
    trust_proxy: bool  # take the client IP from the last X-Forwarded-For hop (only behind a trusted proxy)
    pipeline_timeout: float  # seconds before a run is aborted
    llm_timeout: float  # seconds for the optional Claude memo call
    max_body_bytes: int  # request body size cap


def get_settings() -> Settings:
    return Settings(
        allow_pacing=_bool("AGENTLEDGER_ALLOW_PACING", True),
        server_llm=_bool("AGENTLEDGER_SERVER_LLM", False),
        max_concurrent=_int("AGENTLEDGER_MAX_CONCURRENT", 25),
        rate_limit_per_min=_int("AGENTLEDGER_RATE_LIMIT_PER_MIN", 20),
        trust_proxy=_bool("AGENTLEDGER_TRUST_PROXY", False),
        pipeline_timeout=_float("AGENTLEDGER_PIPELINE_TIMEOUT", 45.0),
        llm_timeout=_float("AGENTLEDGER_LLM_TIMEOUT", 20.0),
        max_body_bytes=_int("AGENTLEDGER_MAX_BODY_BYTES", 16_384),
    )
