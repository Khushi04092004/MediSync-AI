"""
medications.py
--------------
Feature 3: AI-Powered Medication Reminders and Adherence Tracking
Routes registered on a FastAPI router and included in main.py.
"""

from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import database
import auth
import gemini_client

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ReminderCreate(BaseModel):
    medicine_name: str
    dosage: str = ""
    frequency: str = "once_daily"  # once_daily, twice_daily, thrice_daily, four_times_daily, as_needed
    instructions: str = ""
    start_date: str = ""  # YYYY-MM-DD, defaults to today
    end_date: str = ""    # YYYY-MM-DD or empty for ongoing
    reminder_times: list[str] = ["09:00"]  # array of "HH:MM"


class ReminderUpdate(BaseModel):
    medicine_name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    instructions: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    reminder_times: list[str] | None = None


class ActionLogRequest(BaseModel):
    scheduled_datetime: str  # e.g. "2026-10-30 09:00"
    action: str = "taken"    # "taken" or "skipped"


class AIScheduleRequest(BaseModel):
    medicine_name: str
    frequency: str = "twice_daily"
    instructions: str = ""
    wake_time: str = "08:00"
    sleep_time: str = "22:00"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _attach_reminder_times(medication_dict: dict, cur) -> dict:
    cur.execute(
        "SELECT id, reminder_time FROM medication_reminders WHERE medication_id = ? ORDER BY reminder_time",
        (medication_dict["id"],)
    )
    rows = cur.fetchall()
    medication_dict["reminder_times"] = [r["reminder_time"] for r in rows]
    medication_dict["reminder_details"] = [{"id": r["id"], "time": r["reminder_time"]} for r in rows]
    return medication_dict


# ---------------------------------------------------------------------------
# GET /api/reminders — List all medications with reminder times
# ---------------------------------------------------------------------------
@router.get("/api/reminders")
def list_reminders(current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM medications
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
    """, (current_user["id"],))
    meds = [database.row_to_dict(r) for r in cur.fetchall()]

    for med in meds:
        _attach_reminder_times(med, cur)

    conn.close()
    return {"medications": meds}


# ---------------------------------------------------------------------------
# POST /api/reminders — Create new medication reminder
# ---------------------------------------------------------------------------
@router.post("/api/reminders")
def create_reminder(req: ReminderCreate, current_user: dict = Depends(auth.require_auth)):
    if not req.medicine_name.strip():
        raise HTTPException(status_code=400, detail="Medicine name is required")

    start_date = req.start_date.strip() or date.today().isoformat()
    now = datetime.now().isoformat()

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO medications
        (user_id, medicine_name, dosage, frequency, instructions, start_date, end_date, is_active, is_paused, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
    """, (
        current_user["id"], req.medicine_name.strip(), req.dosage.strip(),
        req.frequency, req.instructions.strip(), start_date, req.end_date.strip(), now
    ))
    med_id = cur.lastrowid

    # Insert individual reminder times
    times = req.reminder_times if req.reminder_times else ["09:00"]
    for t in times:
        clean_time = t.strip()
        if clean_time:
            cur.execute("""
                INSERT INTO medication_reminders (medication_id, reminder_time)
                VALUES (?, ?)
            """, (med_id, clean_time))

    conn.commit()
    conn.close()

    return {
        "message": "Medication reminder created successfully",
        "id": med_id,
        "medicine_name": req.medicine_name
    }


# ---------------------------------------------------------------------------
# PUT /api/reminders/{id} — Update medication reminder
# ---------------------------------------------------------------------------
@router.put("/api/reminders/{med_id}")
def update_reminder(med_id: int, req: ReminderUpdate, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Medication not found")

    med = database.row_to_dict(row)
    if med["user_id"] != current_user["id"] and current_user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")

    name = req.medicine_name if req.medicine_name is not None else med["medicine_name"]
    dosage = req.dosage if req.dosage is not None else med["dosage"]
    frequency = req.frequency if req.frequency is not None else med["frequency"]
    instructions = req.instructions if req.instructions is not None else med["instructions"]
    start_date = req.start_date if req.start_date is not None else med["start_date"]
    end_date = req.end_date if req.end_date is not None else med["end_date"]

    cur.execute("""
        UPDATE medications
        SET medicine_name = ?, dosage = ?, frequency = ?, instructions = ?, start_date = ?, end_date = ?
        WHERE id = ?
    """, (name, dosage, frequency, instructions, start_date, end_date, med_id))

    if req.reminder_times is not None:
        cur.execute("DELETE FROM medication_reminders WHERE medication_id = ?", (med_id,))
        for t in req.reminder_times:
            if t.strip():
                cur.execute("INSERT INTO medication_reminders (medication_id, reminder_time) VALUES (?, ?)",
                            (med_id, t.strip()))

    conn.commit()
    conn.close()
    return {"message": "Medication reminder updated successfully"}


# ---------------------------------------------------------------------------
# DELETE /api/reminders/{id} — Delete medication reminder
# ---------------------------------------------------------------------------
@router.delete("/api/reminders/{med_id}")
def delete_reminder(med_id: int, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Medication not found")

    med = database.row_to_dict(row)
    if med["user_id"] != current_user["id"] and current_user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")

    cur.execute("UPDATE medications SET is_active = 0 WHERE id = ?", (med_id,))
    conn.commit()
    conn.close()
    return {"message": "Medication reminder deleted"}


# ---------------------------------------------------------------------------
# PUT /api/reminders/{id}/pause — Pause or resume reminder
# ---------------------------------------------------------------------------
@router.put("/api/reminders/{med_id}/pause")
def toggle_pause_reminder(med_id: int, current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Medication not found")

    med = database.row_to_dict(row)
    if med["user_id"] != current_user["id"] and current_user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")

    new_paused = 0 if med["is_paused"] else 1
    cur.execute("UPDATE medications SET is_paused = ? WHERE id = ?", (new_paused, med_id))
    conn.commit()
    conn.close()
    status_str = "paused" if new_paused else "resumed"
    return {"message": f"Medication reminder {status_str}", "is_paused": bool(new_paused)}


# ---------------------------------------------------------------------------
# GET /api/reminders/due — Get today's doses & status (due, taken, skipped)
# ---------------------------------------------------------------------------
@router.get("/api/reminders/due")
def get_due_reminders(current_user: dict = Depends(auth.require_auth)):
    today_str = date.today().isoformat()
    now_time = datetime.now().strftime("%H:%M")

    conn = database.get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id, m.medicine_name, m.dosage, m.instructions, m.start_date, m.end_date,
               mr.reminder_time, mr.id AS reminder_id
        FROM medications m
        JOIN medication_reminders mr ON mr.medication_id = m.id
        WHERE m.user_id = ? AND m.is_active = 1 AND m.is_paused = 0
          AND (m.start_date <= ?)
          AND (m.end_date = '' OR m.end_date >= ?)
        ORDER BY mr.reminder_time ASC
    """, (current_user["id"], today_str, today_str))

    doses = []
    for r in cur.fetchall():
        row_dict = database.row_to_dict(r)
        sched_dt = f"{today_str} {row_dict['reminder_time']}"

        # Check adherence log for this dose today
        cur.execute("""
            SELECT action, logged_at FROM medication_adherence
            WHERE medication_id = ? AND scheduled_datetime = ?
        """, (row_dict["id"], sched_dt))
        log_row = cur.fetchone()

        if log_row:
            status = log_row["action"]  # "taken" or "skipped"
            logged_at = log_row["logged_at"]
        else:
            status = "due" if row_dict["reminder_time"] <= now_time else "upcoming"
            logged_at = None

        doses.append({
            "medication_id": row_dict["id"],
            "medicine_name": row_dict["medicine_name"],
            "dosage": row_dict["dosage"],
            "instructions": row_dict["instructions"],
            "reminder_time": row_dict["reminder_time"],
            "scheduled_datetime": sched_dt,
            "status": status,
            "logged_at": logged_at
        })

    conn.close()
    return {"today": today_str, "doses": doses}


# ---------------------------------------------------------------------------
# POST /api/reminders/{id}/taken — Log medication taken
# ---------------------------------------------------------------------------
@router.post("/api/reminders/{med_id}/taken")
def log_taken(med_id: int, req: ActionLogRequest, current_user: dict = Depends(auth.require_auth)):
    return _record_adherence(med_id, req.scheduled_datetime, "taken", current_user)


# ---------------------------------------------------------------------------
# POST /api/reminders/{id}/skip — Log medication skipped
# ---------------------------------------------------------------------------
@router.post("/api/reminders/{med_id}/skip")
def log_skipped(med_id: int, req: ActionLogRequest, current_user: dict = Depends(auth.require_auth)):
    return _record_adherence(med_id, req.scheduled_datetime, "skipped", current_user)


def _record_adherence(med_id: int, scheduled_dt: str, action: str, current_user: dict):
    conn = database.get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, user_id FROM medications WHERE id = ?", (med_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Medication not found")
    if row["user_id"] != current_user["id"] and current_user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")

    now = datetime.now().isoformat()

    # Check if record already exists for this scheduled datetime
    cur.execute("""
        SELECT id FROM medication_adherence
        WHERE medication_id = ? AND scheduled_datetime = ?
    """, (med_id, scheduled_dt))
    existing = cur.fetchone()

    if existing:
        cur.execute("""
            UPDATE medication_adherence
            SET action = ?, logged_at = ?
            WHERE id = ?
        """, (action, now, existing["id"]))
    else:
        cur.execute("""
            INSERT INTO medication_adherence (medication_id, user_id, scheduled_datetime, action, logged_at)
            VALUES (?, ?, ?, ?, ?)
        """, (med_id, current_user["id"], scheduled_dt, action, now))

    conn.commit()
    conn.close()
    return {"message": f"Dose marked as {action}", "status": action, "logged_at": now}


# ---------------------------------------------------------------------------
# GET /api/reminders/adherence — Adherence statistics and 30-day logs
# ---------------------------------------------------------------------------
@router.get("/api/reminders/adherence")
def get_adherence_stats(days: int = Query(30, ge=1, le=90), current_user: dict = Depends(auth.require_auth)):
    conn = database.get_connection()
    cur = conn.cursor()

    start_date = (date.today() - timedelta(days=days)).isoformat()

    cur.execute("""
        SELECT ma.*, m.medicine_name, m.dosage
        FROM medication_adherence ma
        JOIN medications m ON m.id = ma.medication_id
        WHERE ma.user_id = ? AND ma.scheduled_datetime >= ?
        ORDER BY ma.scheduled_datetime DESC
    """, (current_user["id"], start_date))
    logs = [database.row_to_dict(r) for r in cur.fetchall()]

    taken_count = sum(1 for log in logs if log["action"] == "taken")
    skipped_count = sum(1 for log in logs if log["action"] == "skipped")
    total_logged = taken_count + skipped_count

    adherence_rate = round((taken_count / total_logged * 100), 1) if total_logged > 0 else 100.0

    conn.close()
    return {
        "days": days,
        "adherence_rate": adherence_rate,
        "taken_count": taken_count,
        "skipped_count": skipped_count,
        "total_logged": total_logged,
        "recent_logs": logs[:20]
    }


# ---------------------------------------------------------------------------
# POST /api/reminders/ai-schedule — Gemini AI calculates optimal dose times
# ---------------------------------------------------------------------------
@router.post("/api/reminders/ai-schedule")
def ai_schedule(req: AIScheduleRequest, current_user: dict = Depends(auth.require_auth)):
    if not req.medicine_name.strip():
        raise HTTPException(status_code=400, detail="Medicine name is required")

    result = gemini_client.generate_reminder_schedule(
        medicine_name=req.medicine_name.strip(),
        frequency=req.frequency,
        instructions=req.instructions,
        wake_time=req.wake_time,
        sleep_time=req.sleep_time
    )
    return result
