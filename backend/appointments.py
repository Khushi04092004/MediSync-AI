"""
appointments.py
---------------
Feature 1: Doctor Appointment Booking System
All routes are registered on the FastAPI router and included in main.py.
No existing files were modified except main.py (import + include_router).
"""

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import database
import auth

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class AppointmentCreate(BaseModel):
    doctor_id: int
    availability_id: int
    appointment_date: str
    appointment_time: str
    reason: str = ""


class AppointmentStatusUpdate(BaseModel):
    status: str   # Pending | Confirmed | Completed | Cancelled
    notes: str = ""


class AvailabilityCreate(BaseModel):
    available_date: str
    start_time: str
    end_time: str
    max_slots: int = 1


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _doctor_id_for_user(user_id: int) -> int | None:
    """Returns the doctors.id for a given users.id, or None."""
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM doctors WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None


def _fmt_doctor(row: dict, conn=None) -> dict:
    """Attach booked slot count to a doctor dict."""
    return row


# ---------------------------------------------------------------------------
# GET /api/doctors — list all active doctors, optional specialization filter
# ---------------------------------------------------------------------------
@router.get("/api/doctors")
def list_doctors(specialization: str = ""):
    conn = database.get_connection()
    cur = conn.cursor()
    if specialization:
        cur.execute("""
            SELECT d.*, u.name, u.email FROM doctors d
            JOIN users u ON u.id = d.user_id
            WHERE d.is_active = 1 AND LOWER(d.specialization) LIKE LOWER(?)
            ORDER BY u.name
        """, (f"%{specialization}%",))
    else:
        cur.execute("""
            SELECT d.*, u.name, u.email FROM doctors d
            JOIN users u ON u.id = d.user_id
            WHERE d.is_active = 1
            ORDER BY u.name
        """)
    doctors = [database.row_to_dict(r) for r in cur.fetchall()]

    # Attach unique specializations for filter dropdown
    cur.execute("SELECT DISTINCT specialization FROM doctors WHERE is_active = 1 ORDER BY specialization")
    specs = [r[0] for r in cur.fetchall()]
    conn.close()
    return {"doctors": doctors, "specializations": specs}


# ---------------------------------------------------------------------------
# GET /api/doctors/{doctor_id} — single doctor profile
# ---------------------------------------------------------------------------
@router.get("/api/doctors/{doctor_id}")
def get_doctor(doctor_id: int):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.*, u.name, u.email FROM doctors d
        JOIN users u ON u.id = d.user_id
        WHERE d.id = ?
    """, (doctor_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return database.row_to_dict(row)


# ---------------------------------------------------------------------------
# GET /api/doctors/{doctor_id}/availability — available dates and slots
# ---------------------------------------------------------------------------
@router.get("/api/doctors/{doctor_id}/availability")
def get_doctor_availability(doctor_id: int):
    conn = database.get_connection()
    cur = conn.cursor()

    # Get all active availability slots on or after today
    today_str = datetime.now().date().isoformat()
    cur.execute("""
        SELECT da.* FROM doctor_availability da
        WHERE da.doctor_id = ? AND da.is_active = 1 AND da.available_date >= ?
        ORDER BY da.available_date, da.start_time
    """, (doctor_id, today_str))
    slots = [database.row_to_dict(r) for r in cur.fetchall()]

    # Mark each slot as booked if an active appointment exists for it
    for slot in slots:
        cur.execute("""
            SELECT COUNT(*) FROM appointments
            WHERE availability_id = ? AND status NOT IN ('Cancelled')
        """, (slot["id"],))
        booked = cur.fetchone()[0]
        slot["booked"] = booked >= slot["max_slots"]

    conn.close()
    return {"slots": slots}


# ---------------------------------------------------------------------------
# POST /api/appointments — book an appointment (patient)
# ---------------------------------------------------------------------------
@router.post("/api/appointments")
def book_appointment(req: AppointmentCreate, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()

    # Verify doctor exists
    cur.execute("SELECT id FROM doctors WHERE id = ? AND is_active = 1", (req.doctor_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Doctor not found or unavailable")

    # Verify the slot exists and belongs to this doctor
    cur.execute("SELECT * FROM doctor_availability WHERE id = ? AND doctor_id = ? AND is_active = 1",
                (req.availability_id, req.doctor_id))
    slot = cur.fetchone()
    if not slot:
        conn.close()
        raise HTTPException(status_code=400, detail="Selected time slot is not available")

    slot_dict = database.row_to_dict(slot)

    # Check for duplicate booking of this slot
    cur.execute("""
        SELECT COUNT(*) FROM appointments
        WHERE availability_id = ? AND status NOT IN ('Cancelled')
    """, (req.availability_id,))
    booked_count = cur.fetchone()[0]
    if booked_count >= slot_dict["max_slots"]:
        conn.close()
        raise HTTPException(status_code=409, detail="This time slot is already fully booked. Please choose another slot.")

    # Check if patient already booked this doctor on same date/time
    cur.execute("""
        SELECT id FROM appointments
        WHERE patient_id = ? AND doctor_id = ? AND appointment_date = ? AND appointment_time = ?
        AND status NOT IN ('Cancelled')
    """, (current_user["id"], req.doctor_id, req.appointment_date, req.appointment_time))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="You already have an appointment with this doctor at the same date and time.")

    now = datetime.now().isoformat()
    uid = "APT-" + secrets.token_hex(5).upper()

    cur.execute("""
        INSERT INTO appointments
        (appointment_uid, patient_id, doctor_id, availability_id, appointment_date, appointment_time, reason, status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', '', ?, ?)
    """, (uid, current_user["id"], req.doctor_id, req.availability_id,
          req.appointment_date, req.appointment_time, req.reason, now, now))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    return {
        "message": "Appointment booked successfully",
        "appointment_id": new_id,
        "appointment_uid": uid,
        "status": "Pending"
    }


# ---------------------------------------------------------------------------
# GET /api/appointments/my — patient views their own appointments
# ---------------------------------------------------------------------------
@router.get("/api/appointments/my")
def my_appointments(current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.*, d.specialization, d.consultation_fee, u.name AS doctor_name
        FROM appointments a
        JOIN doctors d ON d.id = a.doctor_id
        JOIN users u ON u.id = d.user_id
        WHERE a.patient_id = ?
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (current_user["id"],))
    rows = [database.row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"appointments": rows}


# ---------------------------------------------------------------------------
# PUT /api/appointments/{appointment_id}/cancel — patient cancels
# ---------------------------------------------------------------------------
@router.put("/api/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: int, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    appt = cur.fetchone()
    if not appt:
        conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")
    appt_dict = database.row_to_dict(appt)

    # Only the patient who owns it, or an admin, can cancel
    if appt_dict["patient_id"] != current_user["id"] and current_user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="You can only cancel your own appointments")

    if appt_dict["status"] in ("Completed", "Cancelled"):
        conn.close()
        raise HTTPException(status_code=400, detail=f"Cannot cancel an appointment that is already {appt_dict['status']}")

    now = datetime.now().isoformat()
    cur.execute("UPDATE appointments SET status = 'Cancelled', updated_at = ? WHERE id = ?", (now, appointment_id))
    conn.commit()
    conn.close()
    return {"message": "Appointment cancelled successfully"}


# ---------------------------------------------------------------------------
# PUT /api/appointments/{appointment_id}/status — doctor/admin updates status
# ---------------------------------------------------------------------------
@router.put("/api/appointments/{appointment_id}/status")
def update_appointment_status(appointment_id: int, req: AppointmentStatusUpdate,
                               current_user: dict = Depends(auth.require_auth)):
    valid_statuses = ("Pending", "Confirmed", "Completed", "Cancelled")
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    appt = cur.fetchone()
    if not appt:
        conn.close()
        raise HTTPException(status_code=404, detail="Appointment not found")

    appt_dict = database.row_to_dict(appt)

    # Doctors can only update their own appointments; admins can update any
    if current_user["role"] == "doctor":
        doctor_id = _doctor_id_for_user(current_user["id"])
        if appt_dict["doctor_id"] != doctor_id:
            conn.close()
            raise HTTPException(status_code=403, detail="You can only update your own appointments")
    elif current_user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Only doctors and admins can update appointment status")

    now = datetime.now().isoformat()
    cur.execute(
        "UPDATE appointments SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
        (req.status, req.notes, now, appointment_id)
    )
    conn.commit()
    conn.close()
    return {"message": f"Appointment status updated to {req.status}"}


# ---------------------------------------------------------------------------
# GET /api/appointments/doctor — doctor views their own appointments
# ---------------------------------------------------------------------------
@router.get("/api/appointments/doctor")
def doctor_appointments(current_user: dict = Depends(auth.require_doctor)):
    doctor_id = _doctor_id_for_user(current_user["id"])
    if not doctor_id:
        raise HTTPException(status_code=404, detail="Doctor profile not found for this account")

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.*, u.name AS patient_name, u.email AS patient_email
        FROM appointments a
        JOIN users u ON u.id = a.patient_id
        WHERE a.doctor_id = ?
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (doctor_id,))
    rows = [database.row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return {"appointments": rows}


# ---------------------------------------------------------------------------
# POST /api/doctors/{doctor_id}/availability — doctor adds availability
# ---------------------------------------------------------------------------
@router.post("/api/doctors/{doctor_id}/availability")
def add_availability(doctor_id: int, req: AvailabilityCreate,
                     current_user: dict = Depends(auth.require_auth)):
    # Must be the doctor themselves or an admin
    if current_user["role"] == "doctor":
        my_doctor_id = _doctor_id_for_user(current_user["id"])
        if my_doctor_id != doctor_id:
            raise HTTPException(status_code=403, detail="You can only manage your own availability")
    elif current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only doctors or admins can manage availability")

    conn = database.get_connection()
    cur = conn.cursor()

    # Check for duplicate slot
    cur.execute("""
        SELECT id FROM doctor_availability
        WHERE doctor_id = ? AND available_date = ? AND start_time = ? AND is_active = 1
    """, (doctor_id, req.available_date, req.start_time))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="A slot at this date and time already exists")

    cur.execute("""
        INSERT INTO doctor_availability (doctor_id, available_date, start_time, end_time, max_slots, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (doctor_id, req.available_date, req.start_time, req.end_time, req.max_slots))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"message": "Availability slot added", "id": new_id}


# ---------------------------------------------------------------------------
# DELETE /api/doctors/{doctor_id}/availability/{slot_id} — doctor removes slot
# ---------------------------------------------------------------------------
@router.delete("/api/doctors/{doctor_id}/availability/{slot_id}")
def remove_availability(doctor_id: int, slot_id: int,
                        current_user: dict = Depends(auth.require_auth)):
    if current_user["role"] == "doctor":
        my_doctor_id = _doctor_id_for_user(current_user["id"])
        if my_doctor_id != doctor_id:
            raise HTTPException(status_code=403, detail="You can only manage your own availability")
    elif current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only doctors or admins can manage availability")

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE doctor_availability SET is_active = 0 WHERE id = ? AND doctor_id = ?",
                (slot_id, doctor_id))
    conn.commit()
    conn.close()
    return {"message": "Availability slot removed"}


# ---------------------------------------------------------------------------
# GET /api/doctors/profile/me — doctor gets/creates their own profile
# ---------------------------------------------------------------------------
@router.get("/api/doctors/profile/me")
def my_doctor_profile(current_user: dict = Depends(auth.require_doctor)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM doctors WHERE user_id = ?", (current_user["id"],))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"profile": None}
    return {"profile": database.row_to_dict(row)}


# ---------------------------------------------------------------------------
# PUT /api/doctors/profile/me — doctor updates their profile
# ---------------------------------------------------------------------------
class DoctorProfileUpdate(BaseModel):
    specialization: str = ""
    qualifications: str = ""
    experience_years: int = 0
    consultation_fee: float = 0
    description: str = ""


@router.put("/api/doctors/profile/me")
def update_doctor_profile(req: DoctorProfileUpdate, current_user: dict = Depends(auth.require_doctor)):
    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("SELECT id FROM doctors WHERE user_id = ?", (current_user["id"],))
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE doctors SET specialization=?, qualifications=?, experience_years=?,
            consultation_fee=?, description=? WHERE user_id=?
        """, (req.specialization, req.qualifications, req.experience_years,
              req.consultation_fee, req.description, current_user["id"]))
    else:
        cur.execute("""
            INSERT INTO doctors (user_id, specialization, qualifications, experience_years, consultation_fee, description, profile_image_url, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, '', 1, ?)
        """, (current_user["id"], req.specialization, req.qualifications,
              req.experience_years, req.consultation_fee, req.description, now))
    conn.commit()
    conn.close()
    return {"message": "Doctor profile updated"}
