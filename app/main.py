import logging
from fastapi import FastAPI, Request

app = FastAPI(title="InvoicePilot")
log = logging.getLogger("uvicorn.error")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    body = await request.json()
    log.info("PayPal webhook: %s id=%s", body.get("event_type"), body.get("id"))
    return {"received": True}