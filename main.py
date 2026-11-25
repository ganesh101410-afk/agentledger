import json
import logging
import math
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core import __version__
from core.config import get_settings
from core.models import Application
from core.orchestrator import graph_spec, run_pipeline
from core.samples import SAMPLES
from core.security import BodyLimitMiddleware, RateLimiter, SecurityHeadersMiddleware, client_ip

if not logging.getLogger().handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("agentledger")

ROOT = Path(__file__).parent

# /docs and /redoc load scripts from a CDN, which the strict Content-Security-Policy blocks.
# The API is documented in the README, and /openapi.json is still served.
app = FastAPI(title="AgentLedger", version=__version__, docs_url=None, redoc_url=None)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

limiter = RateLimiter()
_active_runs = 0


class UnderwriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application: Application
    api_key: str | None = Field(default=None, max_length=300)  # used for this request only; never stored or logged
    pacing: bool = True

    @field_validator("api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value):
        return value.strip() or None if isinstance(value, str) else value


def _admit(request: Request) -> None:
    """Reject the request with 429 (per-client rate limit) or 503 (server at capacity) before any work starts."""
    settings = get_settings()
    peer = request.client.host if request.client else None
    retry = limiter.check(client_ip(request.headers, peer, settings.trust_proxy), settings.rate_limit_per_min)
    if retry is not None:
        raise HTTPException(429, "Too many requests. Please wait a moment.", headers={"Retry-After": str(math.ceil(retry) or 1)})
    if _active_runs >= settings.max_concurrent:
        raise HTTPException(503, "The server is busy. Please try again shortly.", headers={"Retry-After": "5"})


@contextmanager
def _run_slot():
    global _active_runs
    _active_runs += 1
    try:
        yield
    finally:
        _active_runs -= 1


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    # Never echo the submitted values back: they can contain an API key, or NaN, which is not valid JSON.
    detail = [
        {"field": ".".join(str(p) for p in err["loc"] if p not in ("body", "application")), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse({"detail": detail}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.error("unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse({"detail": "Internal server error."}, status_code=500)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__}


@app.get("/api/samples")
def samples():
    return SAMPLES


@app.get("/api/graph")
def graph():
    return graph_spec()


def _log_run(run_id: str, started: float, outcome: str | None, used_llm: bool) -> None:
    # Deliberately no applicant data and no API key in logs.
    logger.info("run=%s outcome=%s llm=%s ms=%d", run_id, outcome, used_llm, (time.perf_counter() - started) * 1000)


@app.post("/api/underwrite")
async def underwrite(req: UnderwriteRequest, request: Request):
    run_id, started = uuid.uuid4().hex[:8], time.perf_counter()
    _admit(request)
    with _run_slot():
        events = [e async for e in run_pipeline(req.application, req.api_key, pacing=False)]
    complete = next((e for e in events if e["type"] == "complete"), None)
    used_llm = any(e["type"] == "agent_done" and e["result"]["used_llm"] for e in events)
    _log_run(run_id, started, complete["decision"]["outcome"] if complete else None, used_llm)
    return {"events": events, "complete": complete}


@app.post("/api/underwrite/stream")
async def underwrite_stream(req: UnderwriteRequest, request: Request):
    pacing = req.pacing and get_settings().allow_pacing
    run_id, started = uuid.uuid4().hex[:8], time.perf_counter()

    _admit(request)  # fail fast with 429/503 before the stream opens

    async def sse():
        outcome, used_llm = None, False
        with _run_slot():
            try:
                async for event in run_pipeline(req.application, req.api_key, pacing=pacing):
                    if event["type"] == "complete":
                        outcome = event["decision"]["outcome"]
                    elif event["type"] == "agent_done" and event["result"]["used_llm"]:
                        used_llm = True
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                _log_run(run_id, started, outcome, used_llm)

    return StreamingResponse(
        sse(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )
