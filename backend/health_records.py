"""
health_records.py
------------------
Feature 2: Digital Health Records Management
All routes registered on a FastAPI router, included in main.py.
Files are stored in backend/uploads/health_records/<user_id>/ directory.
File paths are never exposed in public URLs; download is gated by auth + ownership check.
"""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database
import auth
import gemini_client
from gemini_client import GeminiError
import config

router = APIRouter()

# ---------------------------------------------------------------------------
# File storage configuration
# ---------------------------------------------------------------------------
UPLOAD_BASE_DIR = os.path.join(os.path.dirname(__file__), "uploads", "health_records")
MAX_FILE_SIZE_MB = 10
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
ALLOWED_CATEGORIES = [
    "Lab Report", "Prescription", "X-Ray / Scan", "Blood Test",
    "Discharge Summary", "Vaccination", "Insurance", "Other"
]


def _user_upload_dir(user_id: int) -> str:
    path = os.path.join(UPLOAD_BASE_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _validate_file(file: UploadFile):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class PatientProfileUpdate(BaseModel):
    date_of_birth: str = ""
    blood_group: str = ""
    gender: str = ""
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""
    known_allergies: str = ""
    existing_conditions: str = ""


# ---------------------------------------------------------------------------
# GET /api/health/profile — get patient's health profile
# ---------------------------------------------------------------------------
@router.get("/api/health/profile")
def get_health_profile(current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM patient_profiles WHERE user_id = ?", (current_user["id"],))
    row = cur.fetchone()
    conn.close()
    profile = database.row_to_dict(row) if row else {}
    return {"profile": profile}


# ---------------------------------------------------------------------------
# PUT /api/health/profile — create or update patient health profile
# ---------------------------------------------------------------------------
@router.put("/api/health/profile")
def update_health_profile(req: PatientProfileUpdate, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("SELECT id FROM patient_profiles WHERE user_id = ?", (current_user["id"],))
    existing = cur.fetchone()
    if existing:
        cur.execute("""
            UPDATE patient_profiles SET date_of_birth=?, blood_group=?, gender=?,
            emergency_contact_name=?, emergency_contact_phone=?,
            known_allergies=?, existing_conditions=?, updated_at=?
            WHERE user_id=?
        """, (req.date_of_birth, req.blood_group, req.gender,
              req.emergency_contact_name, req.emergency_contact_phone,
              req.known_allergies, req.existing_conditions, now, current_user["id"]))
    else:
        cur.execute("""
            INSERT INTO patient_profiles
            (user_id, date_of_birth, blood_group, gender, emergency_contact_name,
             emergency_contact_phone, known_allergies, existing_conditions, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (current_user["id"], req.date_of_birth, req.blood_group, req.gender,
              req.emergency_contact_name, req.emergency_contact_phone,
              req.known_allergies, req.existing_conditions, now))
    conn.commit()
    conn.close()
    return {"message": "Health profile updated"}


# ---------------------------------------------------------------------------
# POST /api/health/records — upload a health document
# ---------------------------------------------------------------------------
@router.post("/api/health/records")
async def upload_health_record(
    file: UploadFile = File(...),
    category: str = Form("Other"),
    current_user: dict = Depends(auth.require_auth)
):
    _validate_file(file)

    if category not in ALLOWED_CATEGORIES:
        category = "Other"

    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds maximum size of {MAX_FILE_SIZE_MB} MB")
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Store with a UUID filename to avoid path traversal and name collisions
    ext = os.path.splitext(file.filename or "file")[1].lower()
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    upload_dir = _user_upload_dir(current_user["id"])
    file_path = os.path.join(upload_dir, stored_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("""
        INSERT INTO health_records (user_id, filename, original_filename, category, file_size, mime_type, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (current_user["id"], stored_filename, file.filename or stored_filename,
          category, file_size, file.content_type or "", now))
    conn.commit()
    record_id = cur.lastrowid
    conn.close()

    return {"message": "File uploaded successfully", "record_id": record_id,
            "filename": file.filename, "category": category}


# ---------------------------------------------------------------------------
# GET /api/health/records — list patient's health records
# ---------------------------------------------------------------------------
@router.get("/api/health/records")
def list_health_records(current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM health_records WHERE user_id = ?
        ORDER BY uploaded_at DESC
    """, (current_user["id"],))
    rows = [database.row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    # Never expose the internal stored filename path; give only the download URL
    for row in rows:
        row["download_url"] = f"/api/health/records/{row['id']}/download"
        row.pop("filename", None)   # hide internal storage name
    return {"records": rows}


# ---------------------------------------------------------------------------
# GET /api/health/records/{record_id}/download — securely download a file
# ---------------------------------------------------------------------------
@router.get("/api/health/records/{record_id}/download")
def download_health_record(record_id: int, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    record = database.row_to_dict(row)

    # Patients can only download their own records; admins can download any
    if record["user_id"] != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    upload_dir = _user_upload_dir(record["user_id"])
    file_path = os.path.join(upload_dir, record["filename"])
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    return FileResponse(
        path=file_path,
        filename=record["original_filename"],
        media_type=record.get("mime_type") or "application/octet-stream"
    )


# ---------------------------------------------------------------------------
# DELETE /api/health/records/{record_id} — delete a health record
# ---------------------------------------------------------------------------
@router.delete("/api/health/records/{record_id}")
def delete_health_record(record_id: int, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Record not found")
    record = database.row_to_dict(row)

    if record["user_id"] != current_user["id"] and current_user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete the physical file
    upload_dir = _user_upload_dir(record["user_id"])
    file_path = os.path.join(upload_dir, record["filename"])
    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
    except OSError:
        pass  # File already gone; still clean up the DB row

    cur.execute("DELETE FROM health_records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return {"message": "Record deleted successfully"}


# ---------------------------------------------------------------------------
# POST /api/health/records/{record_id}/summarize — AI summarize using Gemini
# ---------------------------------------------------------------------------
@router.post("/api/health/records/{record_id}/summarize")
async def summarize_health_record(record_id: int, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM health_records WHERE id = ?", (record_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    record = database.row_to_dict(row)

    if record["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    upload_dir = _user_upload_dir(record["user_id"])
    file_path = os.path.join(upload_dir, record["filename"])
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    mime = record.get("mime_type") or ""

    try:
        if mime == "application/pdf":
            # Extract text from PDF then send to Gemini
            try:
                import pdfplumber, io
                with pdfplumber.open(file_path) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
            except Exception:
                text = ""
            if not text:
                return {
                    "summary": None,
                    "disclaimer": _disclaimer(),
                    "message": "Could not extract text from this PDF. The document may be scanned/image-based. Try uploading an image version.",
                    "demo_mode": config.is_demo_mode()
                }
            summary = gemini_client.summarize_health_document_text(text)
        elif mime.startswith("image/"):
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            summary = gemini_client.summarize_health_document_image(image_bytes, mime)
        else:
            raise HTTPException(status_code=400, detail="Only PDF and image files can be summarized")
    except GeminiError as e:
        raise HTTPException(status_code=502, detail={"message": str(e)})

    return {
        "summary": summary,
        "disclaimer": _disclaimer(),
        "demo_mode": config.is_demo_mode()
    }


def _disclaimer():
    return (
        "⚠️ AI DISCLAIMER: This summary is generated by AI for informational purposes only. "
        "It is NOT a medical diagnosis or professional medical advice. "
        "Always consult a qualified doctor or healthcare professional for medical decisions."
    )


# ---------------------------------------------------------------------------
# GET /api/health/dashboard — aggregated dashboard for the patient
# ---------------------------------------------------------------------------
@router.get("/api/health/dashboard")
def health_dashboard(current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    user_id = current_user["id"]

    # Total health records
    cur.execute("SELECT COUNT(*) FROM health_records WHERE user_id = ?", (user_id,))
    total_records = cur.fetchone()[0]

    # Recent uploads (last 5)
    cur.execute("""
        SELECT id, original_filename, category, uploaded_at FROM health_records
        WHERE user_id = ? ORDER BY uploaded_at DESC LIMIT 5
    """, (user_id,))
    recent_uploads = [database.row_to_dict(r) for r in cur.fetchall()]

    # Upcoming appointments
    today_str = datetime.now().date().isoformat()
    cur.execute("""
        SELECT a.appointment_date, a.appointment_time, a.status, a.appointment_uid,
               u.name AS doctor_name, d.specialization
        FROM appointments a
        JOIN doctors d ON d.id = a.doctor_id
        JOIN users u ON u.id = d.user_id
        WHERE a.patient_id = ? AND a.appointment_date >= ? AND a.status NOT IN ('Cancelled', 'Completed')
        ORDER BY a.appointment_date, a.appointment_time
        LIMIT 5
    """, (user_id, today_str))
    upcoming_appointments = [database.row_to_dict(r) for r in cur.fetchall()]

    # Active medication count
    cur.execute("SELECT COUNT(*) FROM medications WHERE user_id = ? AND is_active = 1 AND is_paused = 0", (user_id,))
    active_medications = cur.fetchone()[0]

    conn.close()
    return {
        "total_records": total_records,
        "recent_uploads": recent_uploads,
        "upcoming_appointments": upcoming_appointments,
        "active_medications": active_medications
    }
