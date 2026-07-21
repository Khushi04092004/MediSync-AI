"""
payment_gateway.py
--------------------
Payment abstraction layer.

DEFAULT BEHAVIOUR (fully tested by me): if no Razorpay keys are set in .env,
this uses the same simulated COD/UPI/Card logic as before - safe, predictable,
good for demos and grading.

OPTIONAL REAL INTEGRATION (Razorpay): if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET
are set in .env, real Razorpay orders are created via their API for UPI/Card
payments (COD never needs a gateway). This part follows Razorpay's documented
REST API shape from my training knowledge, but I do NOT have real Razorpay
credentials to test against - so this path is best-effort / unverified by me.
Test it yourself with Razorpay's TEST MODE keys before trusting it with real money.
"""

import os
import requests

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()

RAZORPAY_ENABLED = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def create_razorpay_order(amount_rupees: float, receipt: str) -> dict:
    """
    Creates a real Razorpay order (amount in paise). Returns the order object,
    which the frontend would hand to Razorpay's checkout.js widget.
    NOTE: unverified without real credentials - see module docstring.
    """
    if not RAZORPAY_ENABLED:
        raise RuntimeError("Razorpay keys are not configured in .env")

    response = requests.post(
        "https://api.razorpay.com/v1/orders",
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
        json={
            "amount": int(amount_rupees * 100),  # Razorpay expects paise
            "currency": "INR",
            "receipt": receipt,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verifies the signature Razorpay sends back after a successful checkout."""
    import hmac
    import hashlib

    if not RAZORPAY_ENABLED:
        return False

    body = f"{order_id}|{payment_id}"
    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)
