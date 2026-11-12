# Duewise

An AI agent that helps small businesses get paid on time with PayPal. Paste a messy message, and Duewise drafts the invoice, you approve it, and PayPal sends it. It tracks payment through verified webhooks, scores each unpaid invoice for late-payment risk with plain-English reasons, and drafts a reminder in the right tone that you approve before it goes out.

Built for the "Build What's Next with PayPal and AI" hackathon. **Sandbox and test data only.**

**Hosted demo:** https://invoicepilot-206j.onrender.com
(The repo is named `invoicepilot`, an earlier working name.)

## How it works

1. **Draft with AI.** Gemini extracts customer, email, items, prices and due date from a free-text message. Missing details are left blank, never invented.
2. **Human approval.** You edit and approve. The app refuses to send an invoice without an email, or with a zero or missing price.
3. **PayPal sends it.** The invoice is created and sent with the PayPal Invoicing API.
4. **Live tracking.** PayPal webhooks (signature-verified) show up in the app as invoices are created, sent and paid. The table reads invoice status directly from PayPal.
5. **Risk score with reasons.** A logistic regression model scores open invoices (for example "overdue by 7 days; little or no payment history with this customer").
6. **Reminders.** Gemini drafts a friendly, firm or urgent reminder based on how overdue the invoice is. You review it, then it is sent through PayPal's invoice reminder.
7. **Demo clock.** A "Fast-forward 7 days" button shows overdue behavior without waiting.

## PayPal features used

- Invoicing API v2: create, send, list, remind
- OAuth 2.0 client credentials
- Webhooks for invoice events, verified with PayPal's `verify-webhook-signature` endpoint
- PayPal sandbox (no real money)

## AI used

- **Google Gemini** (`gemini-3.5-flash-lite`, with automatic fallback to `gemini-3.1-flash-lite` and `gemini-3.6-flash`): structured extraction of invoice details and reminder drafting.
- **scikit-learn logistic regression**: late-payment risk, with per-invoice reasons from the model's feature contributions. **It is trained on synthetic data generated in `app/risk.py`, not real customer data.**
- **Claude** was used as a coding assistant during development.

## Sponsor tools used

- **AG Grid Community**: the invoice table, with sorting, filtering, a wrapped "why" column and a per-row reminder action.
- **Render**: hosts the live demo and receives PayPal's webhooks.


## Run it locally

Requires Python 3.11+.

```bash
git clone https://github.com/NagaDhanushyaRam/invoicepilot.git
cd invoicepilot
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then fill in the values below
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

### Environment variables

| Variable | What it is |
|---|---|
| `GEMINI_API_KEY` | Key from Google AI Studio |
| `GEMINI_MODELS` | Optional. Comma-separated model fallback list |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | From a PayPal **sandbox** REST app (developer.paypal.com) |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` |
| `PAYPAL_WEBHOOK_ID` | ID of the webhook you register for the app |

### PayPal sandbox setup

1. Create a sandbox REST app in the PayPal developer dashboard (the default sandbox Business account works).
2. Register a webhook pointing to `https://<your-public-host>/webhooks/paypal` and subscribe to the Invoicing events. Copy its Webhook ID into `PAYPAL_WEBHOOK_ID`.
3. Webhooks need a public HTTPS URL. Locally you can skip them: everything works except the "live events" list. Or deploy to Render (start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`).

## Try it

1. Paste: `Bill Maria Lopez (maria@example.com) for 3 hours of logo design at $60/hr, due in two weeks`
2. Click **Draft invoice with AI**, review, then **Approve and send via PayPal**.
3. Watch the `CREATED` and `SENT` events appear. To pay, open the invoice link as the sandbox buyer account (see the testing instructions on the Devpost submission).
4. Click **Fast-forward 7 days**, then **Draft reminder** on an overdue invoice.

## Limitations

- Sandbox only. The demo uses one shared sandbox merchant account, so everyone sees the same invoices.
- The demo clock and recent-events list are kept in memory and reset when the server restarts.
- The hosted demo runs on a free tier that can sleep, and requests are rate limited per visitor.
- The risk model is trained on synthetic data and is a demonstration, not a credit-scoring tool.

## License

MIT