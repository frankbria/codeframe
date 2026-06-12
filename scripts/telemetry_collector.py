"""Minimal self-hostable telemetry collector for CodeFRAME beta (issue #616).

Receives event batches from `cf` clients and appends them to a JSONL file —
the cheapest backend that works for beta volume. No database, no auth, no
dashboards; analyze with jq.

Run:
    TELEMETRY_LOG_PATH=/var/lib/codeframe/events.jsonl \
        uvicorn telemetry_collector:app --host 0.0.0.0 --port 8400

Point clients at it:
    export CODEFRAME_TELEMETRY_ENDPOINT=https://your-host:8400/v1/events

See PRIVACY.md at the repo root for what clients send and the retention policy.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

MAX_BATCH_SIZE = 100

LOG_PATH = Path(os.environ.get("TELEMETRY_LOG_PATH", "./telemetry_events.jsonl"))

app = FastAPI(title="CodeFRAME telemetry collector", docs_url=None, redoc_url=None)


class EventBatch(BaseModel):
    events: list[dict]


@app.post("/v1/events", status_code=202)
def ingest(batch: EventBatch) -> dict:
    if len(batch.events) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=413, detail="batch too large")
    received_at = datetime.now(timezone.utc).isoformat()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        for event in batch.events:
            f.write(json.dumps({**event, "received_at": received_at}) + "\n")
    return {"accepted": len(batch.events)}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
