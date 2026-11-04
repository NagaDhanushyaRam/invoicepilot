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