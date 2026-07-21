"""
delivery_provider.py
----------------------
Delivery/courier abstraction layer.

DEFAULT BEHAVIOUR (fully tested by me): "demo" provider - the same simulated
tracking (Placed -> Verified -> Packed -> Out for Delivery -> Delivered) driven
by the frontend's timer calling /api/orders/{id}/advance. No real courier is
booked; nothing leaves warehouse. Good for demos and grading.

OPTIONAL REAL INTEGRATION (Shiprocket): if SHIPROCKET_EMAIL and
SHIPROCKET_PASSWORD are set in .env, real Shiprocket API calls would be used
to book an actual pickup and get a real AWB (tracking) number. This follows
Shiprocket's documented REST API shape from my training knowledge, but I do
NOT have a real Shiprocket business account to test against - so this path
is best-effort / unverified by me. Test it yourself with a Shiprocket test
account before relying on it for real shipments.
"""

import os
import requests

SHIPROCKET_EMAIL = os.getenv("SHIPROCKET_EMAIL", "").strip()
SHIPROCKET_PASSWORD = os.getenv("SHIPROCKET_PASSWORD", "").strip()

SHIPROCKET_ENABLED = bool(SHIPROCKET_EMAIL and SHIPROCKET_PASSWORD)

_cached_token = None


def _get_shiprocket_token() -> str:
    global _cached_token
    if _cached_token:
        return _cached_token

    response = requests.post(
        "https://apiv2.shiprocket.in/v1/external/auth/login",
        json={"email": SHIPROCKET_EMAIL, "password": SHIPROCKET_PASSWORD},
        timeout=20,
    )
    response.raise_for_status()
    _cached_token = response.json()["token"]
    return _cached_token


def book_shipment(order_id: int, address: str, items: list) -> dict:
    """
    Books a real Shiprocket shipment. Returns {"awb_code": "...", "courier_name": "..."}.
    NOTE: unverified without a real Shiprocket account - see module docstring.
    This is a simplified sketch; Shiprocket's real "create order" endpoint needs
    more fields (pickup location, item dimensions/weight, customer phone, pincode
    breakdown, etc.) that you'll need to fill in based on your Shiprocket account setup.
    """
    if not SHIPROCKET_ENABLED:
        raise RuntimeError("Shiprocket credentials are not configured in .env")

    token = _get_shiprocket_token()
    response = requests.post(
        "https://apiv2.shiprocket.in/v1/external/orders/create/adhoc",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "order_id": str(order_id),
            "billing_address": address,
            "order_items": [{"name": item["name"], "units": item["quantity"]} for item in items],
            # Shiprocket needs several more required fields in practice -
            # see their API docs for your specific account configuration.
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return {"awb_code": data.get("awb_code", ""), "courier_name": data.get("courier_name", "")}


def get_provider_status() -> dict:
    return {"provider": "shiprocket" if SHIPROCKET_ENABLED else "demo", "enabled": SHIPROCKET_ENABLED}
