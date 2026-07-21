"""
verification.py
-----------------
Yeh file MediSync AI ka sabse IMPORTANT safety module hai.

Rule: AI kabhi final decision nahi legi. Yeh file database ke against
har medicine ko verify karta hai - AI ki suggestion ke baad bhi.
Sirf jab sab checks pass ho, tabhi dispense_allowed = True hota hai.
"""

from datetime import date, datetime
from database import get_connection, row_to_dict


def verify_medicine(name: str, requested_qty: int = 1) -> dict:
    """
    Ek medicine ke liye 4 checks karta hai:
    1. Medicine database me exist karti hai?
    2. Stock available hai?
    3. Expiry valid hai (expire nahi hui)?
    4. Prescription required hai ya OTC hai? (flag ke liye, block nahi karta - UI ko batata hai)
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medicines WHERE LOWER(name) = LOWER(?)", (name,))
    row = cur.fetchone()
    conn.close()

    steps = []

    if row is None:
        steps.append({"check": "Medicine Found", "passed": False, "detail": f"'{name}' database me nahi mili."})
        return {
            "medicine_name": name,
            "dispense_allowed": False,
            "steps": steps,
            "reason": "NOT_FOUND"
        }

    medicine = row_to_dict(row)
    steps.append({"check": "Medicine Found", "passed": True, "detail": f"Found in Drawer {medicine['drawer_number']}"})

    # Check 2: stock
    stock_ok = medicine["stock"] >= requested_qty
    steps.append({
        "check": "Stock Available",
        "passed": stock_ok,
        "detail": f"Available: {medicine['stock']}, Requested: {requested_qty}"
    })

    # Check 3: expiry
    expiry_ok = True
    try:
        expiry_dt = datetime.strptime(medicine["expiry_date"], "%Y-%m-%d").date()
        expiry_ok = expiry_dt >= date.today()
    except (ValueError, TypeError):
        expiry_ok = False

    steps.append({
        "check": "Expiry Valid",
        "passed": expiry_ok,
        "detail": f"Expiry date: {medicine['expiry_date']}"
    })

    # Check 4: prescription requirement (informational flag)
    requires_prescription = medicine["otc_or_prescription"] == "Prescription"
    steps.append({
        "check": "Prescription Requirement",
        "passed": True,  # yeh check block nahi karta, sirf flag hai
        "detail": "Prescription required" if requires_prescription else "OTC - no prescription needed"
    })

    dispense_allowed = stock_ok and expiry_ok

    reason = "OK"
    if not stock_ok:
        reason = "OUT_OF_STOCK"
    elif not expiry_ok:
        reason = "EXPIRED"

    return {
        "medicine_name": medicine["name"],
        "medicine_id": medicine["id"],
        "drawer_number": medicine["drawer_number"],
        "requires_prescription": requires_prescription,
        "dispense_allowed": dispense_allowed,
        "steps": steps,
        "reason": reason,
    }


def verify_medicine_list(items: list) -> dict:
    """items = [{"name": "Paracetamol", "quantity": 2}, ...]"""
    results = [verify_medicine(item["name"], item.get("quantity", 1)) for item in items]
    all_allowed = all(r["dispense_allowed"] for r in results)
    return {
        "overall_dispense_allowed": all_allowed,
        "items": results
    }
