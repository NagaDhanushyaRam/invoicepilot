from collections import Counter
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

OPEN = {"SENT", "UNPAID", "PARTIALLY_PAID", "PAYMENT_PENDING"}

# Synthetic training data: NOT real customer data.
_rng = np.random.default_rng(42)
_n = 3000
_X = np.column_stack([
    _rng.lognormal(5, 1, _n).clip(10, 5000),  # invoice amount
    _rng.uniform(-30, 60, _n),                # days until due (negative = overdue)
    _rng.poisson(1.5, _n),                    # prior paid invoices from this customer
    _rng.poisson(0.6, _n),                    # other unpaid invoices from this customer
])
_logit = -0.3 + 0.0008 * _X[:, 0] - 0.045 * _X[:, 1] - 0.5 * _X[:, 2] + 0.7 * _X[:, 3]
_y = _rng.random(_n) < 1 / (1 + np.exp(-_logit))
_scaler = StandardScaler().fit(_X)
_model = LogisticRegression().fit(_scaler.transform(_X), _y)


def score(amount, days_to_due, prior_paid, prior_unpaid):
    x = _scaler.transform(np.array([[amount, days_to_due, prior_paid, prior_unpaid]], dtype=float))
    p = _model.predict_proba(x)[0][1]
    contrib = _model.coef_[0] * x[0]
    texts = [
        f"large amount (${amount:,.0f})",
        f"overdue by {-days_to_due} days" if days_to_due < 0 else f"due in {days_to_due} days",
        "little or no payment history with this customer",
        "customer has other unpaid invoices",
    ]
    top = [texts[i] for i in np.argsort(contrib)[::-1][:2] if contrib[i] > 0.05]
    return round(p * 100), "; ".join(top) or "no major risk factors"


def enrich(rows, today):
    paid = Counter(r["recipient"] for r in rows if r["status"] == "PAID")
    open_ = Counter(r["recipient"] for r in rows if r["status"] in OPEN)
    for r in rows:
        r["overdue"], r["risk"], r["reasons"] = False, None, ""
        if r["status"] in OPEN and r.get("due_date"):
            days = (date.fromisoformat(r["due_date"]) - today).days
            r["overdue"] = days < 0
            r["risk"], r["reasons"] = score(
                r["amount"], days, paid[r["recipient"]], open_[r["recipient"]] - 1
            )
    return rows