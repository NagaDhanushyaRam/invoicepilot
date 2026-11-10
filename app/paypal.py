import os
import httpx

BASE = os.environ.get("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")


def get_token() -> str:
    r = httpx.post(
        f"{BASE}/v1/oauth2/token",
        auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"]),
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def verify_webhook(headers, event: dict) -> bool:
    payload = {
        "auth_algo": headers.get("paypal-auth-algo"),
        "cert_url": headers.get("paypal-cert-url"),
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "transmission_time": headers.get("paypal-transmission-time"),
        "webhook_id": os.environ["PAYPAL_WEBHOOK_ID"],
        "webhook_event": event,
    }
    r = httpx.post(
        f"{BASE}/v1/notifications/verify-webhook-signature",
        headers={"Authorization": f"Bearer {get_token()}"},
        json=payload,
        timeout=15,
    )
    return r.status_code == 200 and r.json().get("verification_status") == "SUCCESS"

def _auth():
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}


def create_and_send(d: dict) -> str:
    cur = d["currency"]
    detail = {"currency_code": cur}
    if d.get("due_date"):
        detail["payment_term"] = {"term_type": "DUE_ON_DATE_SPECIFIED", "due_date": d["due_date"]}
    if d.get("note"):
        detail["note"] = d["note"]
    billing = {"email_address": d["customer_email"]}
    if d.get("customer_name"):
        billing["name"] = {"given_name": d["customer_name"]}
    body = {
        "detail": detail,
        "primary_recipients": [{"billing_info": billing}],
        "items": [
            {
                "name": i["name"],
                "quantity": str(i["quantity"]),
                "unit_amount": {"currency_code": cur, "value": f"{i['unit_price']:.2f}"},
            }
            for i in d["items"]
        ],
    }
    h = _auth()
    r = httpx.post(f"{BASE}/v2/invoicing/invoices", headers=h, json=body, timeout=20)
    r.raise_for_status()
    data = r.json()
    inv_id = data.get("id") or data["href"].rsplit("/", 1)[-1]
    s = httpx.post(f"{BASE}/v2/invoicing/invoices/{inv_id}/send", headers=h,
                   json={"send_to_recipient": True, "send_to_invoicer": True}, timeout=20)
    s.raise_for_status()
    return inv_id


def list_invoices() -> list:
    r = httpx.get(f"{BASE}/v2/invoicing/invoices", headers=_auth(), timeout=20,
                  params={"page": 1, "page_size": 50, "total_required": "true"})
    r.raise_for_status()
    return r.json().get("items", [])


def to_row(inv: dict) -> dict:
    d = inv.get("detail", {})
    rec = (inv.get("primary_recipients") or [{}])[0].get("billing_info", {})
    amt = inv.get("amount", {})
    return {
        "id": inv.get("id"),
        "number": d.get("invoice_number"),
        "status": inv.get("status"),
        "recipient": rec.get("email_address"),
        "amount": float(amt.get("value", 0)),
        "currency": amt.get("currency_code"),
        "due_date": (d.get("payment_term") or {}).get("due_date"),
    }