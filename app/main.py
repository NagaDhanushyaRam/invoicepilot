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

class DraftReq(BaseModel):
    id: str


class SendReq(BaseModel):
    id: str
    subject: str
    body: str


def _find_open(inv_id: str):
    rows = risk.enrich([paypal.to_row(i) for i in paypal.list_invoices()], today())
    for r in rows:
        if r["id"] == inv_id and r["risk"] is not None:
            return r
    return None


@app.post("/api/reminder/draft")
async def api_reminder_draft(body: DraftReq):
    row = await run_in_threadpool(_find_open, body.id)
    if not row:
        raise HTTPException(404, "Open invoice with a due date not found")
    days = (date.fromisoformat(row["due_date"]) - today()).days
    tone = "friendly" if days >= 0 else ("firm but polite" if days >= -14 else "urgent but professional")
    try:
        r = await run_in_threadpool(
            llm.draft_reminder, row["number"], row["recipient"], row["amount"],
            row["currency"], row["due_date"], days, tone,
        )
    except Exception:
        log.exception("reminder draft failed")
        raise HTTPException(503, "The AI service is busy. Please try again in a moment.")
    return {"subject": r.subject, "body": r.body, "tone": tone}


@app.post("/api/reminder/send")
async def api_reminder_send(body: SendReq):
    if not body.subject.strip() or not body.body.strip() or len(body.subject) > 150 or len(body.body) > 1000:
        raise HTTPException(422, "Subject and message are required (subject max 150, message max 1000 characters)")
    try:
        await run_in_threadpool(paypal.send_reminder, body.id, body.subject, body.body)
    except httpx.HTTPStatusError as e:
        log.error("PayPal reminder error: %s", e.response.text[:500])
        raise HTTPException(502, f"PayPal rejected the reminder: {e.response.text[:200]}")
    return {"sent": True}