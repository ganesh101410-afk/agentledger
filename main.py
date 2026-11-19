import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.models import Application
from core.orchestrator import graph_spec, run_pipeline
from core.samples import SAMPLES

ROOT = Path(__file__).parent
app = FastAPI(title="AgentLedger")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class UnderwriteRequest(BaseModel):
    application: Application
    api_key: str | None = None  # used for this request only; never stored or logged
    pacing: bool = True


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/samples")
def samples():
    return SAMPLES


@app.get("/api/graph")
def graph():
    return graph_spec()


@app.post("/api/underwrite")
async def underwrite(req: UnderwriteRequest):
    events = [e async for e in run_pipeline(req.application, req.api_key, pacing=False)]
    return {"events": events, "complete": next((e for e in events if e["type"] == "complete"), None)}


@app.post("/api/underwrite/stream")
async def underwrite_stream(req: UnderwriteRequest):
    async def sse():
        async for event in run_pipeline(req.application, req.api_key, pacing=req.pacing):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
