"""
main.py
--------
This is the MediSync AI main server. To run it, in the terminal type:

    uvicorn main:app --host 127.0.0.1 --port 8000

Then open your browser at: http://127.0.0.1:8000

NOTE: Don't add --reload for normal use. --reload watches this folder for file
changes and restarts the server automatically - but this app also WRITES to
files in this folder (the medisync.db database, every time stock changes or
an order is placed). That combination causes the server to restart mid-request,
which is what causes "Something went wrong" errors. Only use --reload while
you are actively editing the Python code yourself.
"""

import os
import io
from datetime import date, datetime, timedelta

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database
import gemini_client
from gemini_client import GeminiError
import verification
import orders
import config
import auth
import qr_decode

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="MediSync AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

database.init_db()

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def _gemini_error_response(e: GeminiError):
    raise HTTPException(status_code=502, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# Pydantic models (request body shapes)
# ---------------------------------------------------------------------------
class MedicineIn(BaseModel):
    name: str
    generic_name: str = ""
    brand: str = ""
    strength: str = ""
    category: str = ""
    otc_or_prescription: str = "OTC"
    stock: int = 0
    drawer_number: str = ""
    expiry_date: str = ""
    price: float = 0


class MedicineUpdate(BaseModel):
    stock: int | None = None
    expiry_date: str | None = None
    drawer_number: str | None = None
    price: float | None = None


class SelfCareRequest(BaseModel):
    symptoms: list[str]
    age: int
    weight: float | None = None
    pregnancy: bool = False
    allergy: str = ""
    diabetes: bool = False
    blood_pressure: str = ""
    language: str = "en"


class VerifyItem(BaseModel):
    name: str
    quantity: int = 1


class VerifyRequest(BaseModel):
    items: list[VerifyItem]


class DispenseRequest(BaseModel):
    items: list[VerifyItem]
    timing_note: str = ""  # e.g. "Morning: 1, Night: 1, Duration: 5 Days"


class DigitalPrescriptionText(BaseModel):
    text: str
    language: str = "en"


class OrderRequest(BaseModel):
    items: list[VerifyItem]
    address: str
    payment_method: str = "COD"  # "COD" | "UPI" | "Card"
    card_number: str = ""
    upi_id: str = ""
    prescription_medicine_names: list[str] = []  # names extracted from an uploaded prescription scan


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    language: str = "en"


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    admin_code: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


# ---------------------------------------------------------------------------
# Authentication: signup / login / logout
# ---------------------------------------------------------------------------
@app.post("/api/auth/signup")
def signup(req: SignupRequest):
    if not req.name.strip() or not req.email.strip() or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Name, email, and a password of at least 6 characters are required.")
    try:
        user = auth.create_user(req.name.strip(), req.email.strip(), req.password, req.admin_code.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth.create_session(user["id"])
    return {"token": token, "user": user}


@app.post("/api/auth/login")
def login(req: LoginRequest):
    try:
        user = auth.verify_user(req.email.strip(), req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    token = auth.create_session(user["id"])
    return {"token": token, "user": user}


@app.post("/api/auth/logout")
def logout(current_user: dict = Depends(auth.require_auth), authorization: str = Header(None)):
    token = authorization.replace("Bearer ", "").strip()
    auth.delete_session(token)
    return {"message": "Logged out"}


@app.get("/api/auth/me")
def me(current_user: dict = Depends(auth.require_auth)):
    return current_user


# ---------------------------------------------------------------------------
# MODULE 3: Medicine Database + Inventory (CRUD)
# ---------------------------------------------------------------------------
@app.get("/api/medicines")
def list_medicines(search: str = ""):
    conn = database.get_connection()
    cur = conn.cursor()
    if search:
        cur.execute(
            "SELECT * FROM medicines WHERE name LIKE ? OR generic_name LIKE ? OR brand LIKE ? ORDER BY name",
            (f"%{search}%", f"%{search}%", f"%{search}%"),
        )
    else:
        cur.execute("SELECT * FROM medicines ORDER BY name")
    rows = [database.row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"medicines": rows}


@app.post("/api/medicines")
def add_medicine(medicine: MedicineIn, current_user: dict = Depends(auth.require_admin)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO medicines (name, generic_name, brand, strength, category, otc_or_prescription, stock, drawer_number, expiry_date, price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (medicine.name, medicine.generic_name, medicine.brand, medicine.strength, medicine.category,
          medicine.otc_or_prescription, medicine.stock, medicine.drawer_number, medicine.expiry_date, medicine.price))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "message": "Medicine added"}


@app.put("/api/medicines/{medicine_id}")
def update_medicine(medicine_id: int, update: MedicineUpdate, current_user: dict = Depends(auth.require_admin)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,))
    if cur.fetchone() is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Medicine not found")

    fields = update.dict(exclude_unset=True)
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        cur.execute(f"UPDATE medicines SET {set_clause} WHERE id = ?", (*fields.values(), medicine_id))
        conn.commit()
    conn.close()
    return {"message": "Medicine updated"}


@app.delete("/api/medicines/{medicine_id}")
def delete_medicine(medicine_id: int, current_user: dict = Depends(auth.require_admin)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM medicines WHERE id = ?", (medicine_id,))
    conn.commit()
    conn.close()
    return {"message": "Medicine deleted"}


@app.get("/api/inventory/summary")
def inventory_summary():
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medicines")
    rows = [database.row_to_dict(r) for r in cur.fetchall()]
    conn.close()

    today = date.today()
    total_stock = sum(m["stock"] for m in rows)
    low_stock = [m for m in rows if m["stock"] < 10]
    expired = []
    for m in rows:
        try:
            exp = datetime.strptime(m["expiry_date"], "%Y-%m-%d").date()
            if exp < today:
                expired.append(m)
        except (ValueError, TypeError):
            pass

    return {
        "total_medicines": len(rows),
        "total_stock_units": total_stock,
        "low_stock": low_stock,
        "expired": expired,
    }


# ---------------------------------------------------------------------------
# MODULE 1: Scan Prescription
# ---------------------------------------------------------------------------
@app.post("/api/scan/image")
async def scan_handwritten_image(file: UploadFile = File(...), language: str = Form("en"),
                                  current_user: dict = Depends(auth.require_auth)):
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"
    try:
        result = gemini_client.analyze_prescription_image(image_bytes, mime_type, language)
    except GeminiError as e:
        _gemini_error_response(e)
    result = _attach_db_confidence(result)
    return result


@app.post("/api/scan/pdf")
async def scan_digital_pdf(file: UploadFile = File(...), language: str = Form("en"),
                            current_user: dict = Depends(auth.require_auth)):
    pdf_bytes = await file.read()
    raw_text = _extract_pdf_text(pdf_bytes)
    try:
        result = gemini_client.parse_digital_prescription_text(raw_text, language)
    except GeminiError as e:
        _gemini_error_response(e)
    result = _attach_db_confidence(result)
    result["extracted_raw_text_preview"] = raw_text[:300]
    return result


@app.post("/api/scan/text")
def scan_digital_text(payload: DigitalPrescriptionText, current_user: dict = Depends(auth.require_auth)):
    """For when the frontend already extracted text from a PDF/QR itself."""
    try:
        result = gemini_client.parse_digital_prescription_text(payload.text, payload.language)
    except GeminiError as e:
        _gemini_error_response(e)
    result = _attach_db_confidence(result)
    return result


@app.post("/api/scan/qr")
async def scan_qr_code(file: UploadFile = File(...), language: str = Form("en"),
                        current_user: dict = Depends(auth.require_auth)):
    """Decodes a QR code from an uploaded image, then parses it like a digital prescription."""
    image_bytes = await file.read()
    try:
        decoded_text = qr_decode.decode_qr_from_image(image_bytes)
    except qr_decode.QRDecodeError as e:
        raise HTTPException(status_code=422, detail={"message": str(e)})

    try:
        result = gemini_client.parse_digital_prescription_text(decoded_text, language)
    except GeminiError as e:
        _gemini_error_response(e)
    result = _attach_db_confidence(result)
    result["decoded_qr_text_preview"] = decoded_text[:300]
    return result


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def _attach_db_confidence(result: dict) -> dict:
    """
    Cross-checks each extracted medicine against the database to compute confidence.
    This is OUR OWN confidence score (combined with Gemini's raw_confidence),
    because an AI's self-reported confidence is never fully trustworthy on its own.
    """
    medicines = result.get("medicines", [])
    conn = database.get_connection()
    cur = conn.cursor()
    matched_count = 0
    for med in medicines:
        cur.execute("SELECT * FROM medicines WHERE LOWER(name) LIKE LOWER(?)", (f"%{med['name']}%",))
        db_match = cur.fetchone()
        med["found_in_database"] = db_match is not None
        if db_match:
            matched_count += 1
    conn.close()

    match_ratio = (matched_count / len(medicines)) if medicines else 0
    ai_confidence = result.get("raw_confidence", 0.5)
    final_confidence = round((match_ratio * 0.6) + (ai_confidence * 0.4), 2)

    result["final_confidence"] = final_confidence
    result["needs_pharmacist_review"] = final_confidence < 0.6 or len(medicines) == 0
    return result


# ---------------------------------------------------------------------------
# MODULE 2: Self-Care Assistant
# ---------------------------------------------------------------------------
@app.post("/api/selfcare/recommend")
def selfcare_recommend(req: SelfCareRequest, current_user: dict = Depends(auth.require_auth)):
    patient_info = {
        "age": req.age,
        "weight": req.weight,
        "pregnancy": req.pregnancy,
        "allergy": req.allergy,
        "diabetes": req.diabetes,
        "blood_pressure": req.blood_pressure,
    }
    try:
        result = gemini_client.get_otc_recommendation(req.symptoms, patient_info, req.language)
    except GeminiError as e:
        _gemini_error_response(e)
    return result


# ---------------------------------------------------------------------------
# MODULE 4 & 5: AI Verification + Dispensing (simulation)
# ---------------------------------------------------------------------------
@app.post("/api/verify")
def verify_items(req: VerifyRequest):
    items = [item.dict() for item in req.items]
    return verification.verify_medicine_list(items)


@app.post("/api/dispense")
def dispense_items(req: DispenseRequest, current_user: dict = Depends(auth.require_auth)):
    """
    Verifies first; stock is only reduced if every check passes.
    This isn't real hardware - it updates stock and generates a label,
    while the frontend shows an animation that looks like real dispensing.
    """
    items = [item.dict() for item in req.items]
    verification_result = verification.verify_medicine_list(items)

    if not verification_result["overall_dispense_allowed"]:
        raise HTTPException(
            status_code=400,
            detail={"message": "Verification failed - dispensing blocked.", "verification": verification_result}
        )

    conn = database.get_connection()
    cur = conn.cursor()
    for item in items:
        cur.execute("UPDATE medicines SET stock = stock - ? WHERE LOWER(name) = LOWER(?)",
                    (item["quantity"], item["name"]))
    conn.commit()
    conn.close()

    drawers = [r["drawer_number"] for r in verification_result["items"]]

    return {
        "message": "Dispensed successfully",
        "drawers_opened": drawers,
        "label": {
            "medicines": [item["name"] for item in items],
            "timing_note": req.timing_note or "As directed by AI / pharmacist",
        }
    }


# ---------------------------------------------------------------------------
# MODULE 7: Order Medicine Online (browse -> cart -> payment -> delivery)
# ---------------------------------------------------------------------------
@app.get("/api/catalog")
def get_catalog(search: str = ""):
    conn = database.get_connection()
    cur = conn.cursor()
    if search:
        cur.execute("SELECT * FROM medicines WHERE name LIKE ? OR category LIKE ? ORDER BY name",
                    (f"%{search}%", f"%{search}%"))
    else:
        cur.execute("SELECT * FROM medicines ORDER BY name")
    rows = [database.row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"catalog": rows}


@app.post("/api/orders")
def place_order(req: OrderRequest, current_user: dict = Depends(auth.require_auth)):
    items = [item.dict() for item in req.items]
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    if not req.address.strip():
        raise HTTPException(status_code=400, detail="Delivery address is required")
    if req.payment_method not in ("COD", "UPI", "Card"):
        raise HTTPException(status_code=400, detail="Invalid payment method")

    # Safety rule: any Prescription-category medicine in the cart must be confirmed
    # by a name that was actually extracted from an uploaded prescription scan.
    conn = database.get_connection()
    cur = conn.cursor()
    unconfirmed_rx_items = []
    for item in items:
        cur.execute("SELECT otc_or_prescription FROM medicines WHERE LOWER(name) = LOWER(?)", (item["name"],))
        row = cur.fetchone()
        if row and row["otc_or_prescription"] == "Prescription":
            confirmed = any(item["name"].lower() in extracted.lower() or extracted.lower() in item["name"].lower()
                             for extracted in req.prescription_medicine_names)
            if not confirmed:
                unconfirmed_rx_items.append(item["name"])
    conn.close()

    if unconfirmed_rx_items:
        raise HTTPException(status_code=400, detail={
            "message": f"Please upload a valid prescription for: {', '.join(unconfirmed_rx_items)}",
            "requires_prescription_for": unconfirmed_rx_items,
        })

    result = orders.create_order(items, req.address, req.payment_method, req.card_number, req.upi_id)
    if not result["success"]:
        if result["reason"] == "payment_failed":
            message = result["payment_error"]
        else:
            message = "Verification failed - order blocked."
        raise HTTPException(status_code=400, detail={"message": message, "verification": result["verification"]})
    return result


@app.get("/api/orders/{order_id}")
def get_order(order_id: int):
    order = orders.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.post("/api/orders/{order_id}/advance")
def advance_order(order_id: int):
    order = orders.advance_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/api/orders")
def all_orders():
    return {"orders": orders.list_orders()}


# ---------------------------------------------------------------------------
# MODULE 8: Chatbot
# ---------------------------------------------------------------------------
@app.post("/api/chatbot")
def chatbot(req: ChatRequest, current_user: dict = Depends(auth.require_auth)):
    history = [h.dict() for h in req.history]
    try:
        result = gemini_client.chat_reply(history, req.message, req.language)
    except GeminiError as e:
        _gemini_error_response(e)
    return result


# ---------------------------------------------------------------------------
# Settings status (read-only - the key itself lives in .env, see README)
# ---------------------------------------------------------------------------
@app.get("/api/settings/gemini-status")
def gemini_status():
    return {"connected": not config.is_demo_mode(), "model": config.get_gemini_model()}


# ---------------------------------------------------------------------------
# Serve frontend (HTML/CSS/JS) - keep this LAST so /api routes take priority
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
