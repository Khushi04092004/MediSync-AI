"""
orders.py
----------
Handles the "Order Medicine Online" flow:
  Cart -> Verification (reuses the same safety checks as the dispensing machine)
       -> Payment (Cash on Delivery / UPI / Card - all simulated, no real gateway)
       -> Order Created -> Delivery status progresses over time

Nothing here bypasses the safety rule: an order is only created if every item
passes the same Found / Stock / Expiry checks used elsewhere in the app.
"""

import json
from datetime import datetime

from database import get_connection, row_to_dict
import verification

STATUS_SEQUENCE = ["Placed", "Verified", "Packed", "Out for Delivery", "Delivered"]


def get_prices(items: list) -> dict:
    """name (lowercase) -> price lookup from the medicines table."""
    conn = get_connection()
    cur = conn.cursor()
    prices = {}
    for item in items:
        cur.execute("SELECT price FROM medicines WHERE LOWER(name) = LOWER(?)", (item["name"],))
        row = cur.fetchone()
        prices[item["name"].lower()] = row["price"] if row else 0
    conn.close()
    return prices


def _process_payment(payment_method: str, total: float, card_number: str = "", upi_id: str = "") -> dict:
    """
    Simulates a payment gateway. No real money moves - this is a demo.
      - Cash on Delivery: always succeeds, nothing to pay upfront.
      - UPI: succeeds unless the UPI id is empty or obviously invalid.
      - Card: succeeds unless the card number ends in "0000" (demo-only decline test).
    """
    if payment_method == "COD":
        return {"success": True, "status_label": "Pending (Cash on Delivery)"}

    if payment_method == "UPI":
        if not upi_id or "@" not in upi_id:
            return {"success": False, "error": "Please enter a valid UPI ID (e.g. name@bank)."}
        return {"success": True, "status_label": "Paid via UPI"}

    if payment_method == "Card":
        digits = card_number.replace(" ", "")
        if len(digits) < 12:
            return {"success": False, "error": "Please enter a valid card number."}
        if digits.endswith("0000"):
            return {"success": False, "error": "Card declined by bank (demo: numbers ending in 0000 simulate a decline)."}
        return {"success": True, "status_label": "Paid via Card"}

    return {"success": False, "error": "Unknown payment method."}


def create_order(items: list, address: str, payment_method: str,
                  card_number: str = "", upi_id: str = "") -> dict:
    """
    items = [{"name": "Paracetamol", "quantity": 2}, ...]
    Returns either {"success": True, "order": {...}} or
    {"success": False, "reason": "...", "verification": {...}}
    """
    verification_result = verification.verify_medicine_list(items)
    if not verification_result["overall_dispense_allowed"]:
        return {"success": False, "reason": "verification_failed", "verification": verification_result}

    prices = get_prices(items)
    total = sum(prices.get(item["name"].lower(), 0) * item["quantity"] for item in items)

    payment_result = _process_payment(payment_method, total, card_number, upi_id)
    if not payment_result["success"]:
        return {"success": False, "reason": "payment_failed", "payment_error": payment_result["error"],
                "verification": verification_result}

    conn = get_connection()
    cur = conn.cursor()
    for item in items:
        cur.execute("UPDATE medicines SET stock = stock - ? WHERE LOWER(name) = LOWER(?)",
                    (item["quantity"], item["name"]))

    items_with_price = [
        {**item, "unit_price": prices.get(item["name"].lower(), 0)}
        for item in items
    ]

    cur.execute("""
        INSERT INTO orders (items_json, total_amount, address, payment_status, order_status, created_at)
        VALUES (?, ?, ?, ?, 'Placed', ?)
    """, (json.dumps(items_with_price), total, address, payment_result["status_label"], datetime.now().isoformat()))
    conn.commit()
    order_id = cur.lastrowid
    conn.close()

    return {"success": True, "order": get_order(order_id), "verification": verification_result}


def get_order(order_id: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    order = row_to_dict(row)
    order["items"] = json.loads(order["items_json"])
    del order["items_json"]
    return order


def list_orders() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY id DESC")
    rows = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    for order in rows:
        order["items"] = json.loads(order["items_json"])
        del order["items_json"]
    return rows


def advance_order(order_id: int) -> dict:
    """Moves an order to the next delivery status. Used by the frontend's demo timer."""
    order = get_order(order_id)
    if order is None:
        return None
    current_index = STATUS_SEQUENCE.index(order["order_status"])
    if current_index < len(STATUS_SEQUENCE) - 1:
        new_status = STATUS_SEQUENCE[current_index + 1]
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET order_status = ? WHERE id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        order["order_status"] = new_status
    return order
