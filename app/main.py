import logging
from collections import deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import llm, paypal

app = FastAPI(title="Duewise")
log = logging.getLogger("uvicorn.error")
EVENTS = deque(maxlen=20)  # recent verified PayPal events, kept in memory
INDEX = Path(__file__).parent / "static" / "index.html"


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


@app.post("/api/invoices")
async def api_create(draft: llm.InvoiceDraft):
    if not draft.customer_email or not draft.items:
        raise HTTPException(422, "A customer email and at least one item are required")
    if any(i.quantity < 1 or i.unit_price <= 0 for i in draft.items):
        raise HTTPException(422, "Every item needs a quantity of at least 1 and a price above 0")
    try:
        inv_id = await run_in_threadpool(paypal.create_and_send, draft.model_dump())
    except httpx.HTTPStatusError as e:
        log.error("PayPal error: %s", e.response.text[:500])
        raise HTTPException(502, f"PayPal rejected the invoice: {e.response.text[:200]}")
    return {"id": inv_id}


@app.get("/api/invoices")
async def api_invoices():
    items = await run_in_threadpool(paypal.list_invoices)
    return [paypal.to_row(i) for i in items]


@app.get("/api/events")
def api_events():
    return list(EVENTS)