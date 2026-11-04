import logging
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app import paypal

app = FastAPI(title="InvoicePilot")
log = logging.getLogger("uvicorn.error")


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
    return {"received": True}