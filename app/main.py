import logging
from collections import deque
from pathlib import Path
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import llm, paypal, risk

app = FastAPI(title="Duewise")
log = logging.getLogger("uvicorn.error")
EVENTS = deque(maxlen=20)  # recent verified PayPal events, kept in memory
CLOCK = {"offset": 0}
INDEX = Path(__file__).parent / "static" / "index.html"

def today():
    return date.today() + timedelta(days=CLOCK["offset"])
class Message(BaseModel):
    message: str


@app.get("/")
def home():
    return FileResponse(INDEX)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    event = await request.json()
    ok = await run_in_threadpool(paypal.verify_webhook, request.headers, event)
    if not ok:
        log.warning("Rejected unverified webhook: %s", event.get("event_type"))
        raise HTTPException(status_code=400, detail="invalid signature")
    log.info("PayPal webhook verified: %s id=%s", event.get("event_type"), event.get("id"))
    EVENTS.appendleft({"type": event.get("event_type"), "time": event.get("create_time")})
    return {"received": True}


@app.post("/api/extract")
async def api_extract(body: Message):
    if len(body.message) > 2000:
        raise HTTPException(413, "Message too long")
    try:
        draft = await run_in_threadpool(llm.extract_invoice, body.message)
    except Exception:
        log.exception("extract failed")
        raise HTTPException(503, "The AI service is busy. Please try again in a moment.")
    return draft.model_dump()

@app.get("/api/invoices")
async def api_invoices():
      items = await run_in_threadpool(paypal.list_invoices)
      rows = [paypal.to_row(i) for i in items]
      return risk.enrich(rows, today())

@app.get("/api/clock")
def get_clock():
      return {"today": today().isoformat(), "offset": CLOCK["offset"]}


@app.post("/api/clock/advance")
def advance_clock(days: int = 7):
      CLOCK["offset"] += days
      return get_clock()


@app.post("/api/clock/reset")
def reset_clock():
      CLOCK["offset"] = 0
      return get_clock()

@app.get("/api/events")
def api_events():
    return list(EVENTS)