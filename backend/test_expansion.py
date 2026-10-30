"""
test_expansion.py
-----------------
Automated test suite verifying the 3 major features of MediSync AI:
1. Doctor Appointment Booking System
2. Digital Health Records Management
3. AI-Powered Medication Reminders
"""

import io
import sys
import os

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient

import main
import auth
import database

client = TestClient(main.app)

def run_tests():
    print("========================================")
    print("Testing MediSync AI Platform Expansion")
    print("========================================")

    # 1. Setup test users
    patient_email = "testpatient@medisync.ai"
    doctor_email = "testdoctor@medisync.ai"
    password = "TestPassword123"

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE email IN (?, ?)", (patient_email, doctor_email))
    conn.commit()
    conn.close()

    # Signup Patient
    res = client.post("/api/auth/signup", json={"name": "Alice Patient", "email": patient_email, "password": password})
    assert res.status_code == 200, f"Patient signup failed: {res.text}"
    patient_token = res.json()["token"]
    patient_headers = {"Authorization": f"Bearer {patient_token}"}
    print("✅ Patient signup & auth token verified")

    # Signup Doctor
    auth.DOCTOR_SIGNUP_CODE = "DOC123"
    res = client.post("/api/auth/signup", json={"name": "Dr. Bob Surgeon", "email": doctor_email, "password": password, "admin_code": "DOC123"})
    assert res.status_code == 200, f"Doctor signup failed: {res.text}"
    doctor_token = res.json()["token"]
    doctor_headers = {"Authorization": f"Bearer {doctor_token}"}
    print("✅ Doctor signup & doctor role verified")

    # ----------------------------------------------------
    # FEATURE 1: Doctor Appointment Booking System
    # ----------------------------------------------------
    print("\n--- Testing Feature 1: Doctor Appointments ---")
    # 1.1 List doctors
    res = client.get("/api/doctors")
    assert res.status_code == 200
    doctors = res.json()["doctors"]
    assert len(doctors) > 0, "No doctors seeded"
    doc_id = doctors[0]["id"]
    print(f"✅ Listed {len(doctors)} doctors. Found doctor ID: {doc_id} ({doctors[0]['name']})")

    # 1.2 Get doctor detail & availability
    res = client.get(f"/api/doctors/{doc_id}")
    assert res.status_code == 200
    assert res.json()["id"] == doc_id

    res = client.get(f"/api/doctors/{doc_id}/availability")
    assert res.status_code == 200
    slots = res.json()["slots"]
    assert len(slots) > 0, "No availability slots for doctor"
    slot = slots[0]
    slot_id = slot["id"]
    print(f"✅ Doctor slot found: {slot['available_date']} at {slot['start_time']}")

    # 1.3 Patient books appointment
    res = client.post("/api/appointments", json={
        "doctor_id": doc_id,
        "availability_id": slot_id,
        "appointment_date": slot["available_date"],
        "appointment_time": slot["start_time"],
        "reason": "Routine cardiac checkup"
    }, headers=patient_headers)
    assert res.status_code == 200, f"Booking failed: {res.text}"
    booking_data = res.json()
    appt_id = booking_data["appointment_id"]
    appt_uid = booking_data["appointment_uid"]
    print(f"✅ Booked appointment successfully! Ref: {appt_uid}")

    # 1.4 Patient views their appointments
    res = client.get("/api/appointments/my", headers=patient_headers)
    assert res.status_code == 200
    my_appts = res.json()["appointments"]
    assert any(a["id"] == appt_id for a in my_appts)
    print("✅ Appointment appears in patient's list")

    # 1.5 Doctor profile and availability management
    res = client.put("/api/doctors/profile/me", json={
        "specialization": "Cardiologist",
        "qualifications": "MBBS, MD",
        "experience_years": 12,
        "consultation_fee": 700,
        "description": "Specialist in preventative cardiology"
    }, headers=doctor_headers)
    assert res.status_code == 200
    print("✅ Doctor updated practice profile")

    # 1.6 Doctor adds availability slot
    res = client.get("/api/doctors/profile/me", headers=doctor_headers)
    my_doc_id = res.json()["profile"]["id"]
    res = client.post(f"/api/doctors/{my_doc_id}/availability", json={
        "available_date": "2026-11-15",
        "start_time": "14:00",
        "end_time": "15:00",
        "max_slots": 2
    }, headers=doctor_headers)
    assert res.status_code == 200
    new_slot_id = res.json()["id"]
    print("✅ Doctor added new availability slot")

    # 1.7 Doctor removes availability slot
    res = client.delete(f"/api/doctors/{my_doc_id}/availability/{new_slot_id}", headers=doctor_headers)
    assert res.status_code == 200
    print("✅ Doctor removed availability slot")

    # 1.8 Patient cancels appointment
    res = client.put(f"/api/appointments/{appt_id}/cancel", headers=patient_headers)
    assert res.status_code == 200
    print("✅ Patient cancelled appointment successfully")

    # ----------------------------------------------------
    # FEATURE 2: Digital Health Records Management
    # ----------------------------------------------------
    print("\n--- Testing Feature 2: Digital Health Records ---")
    # 2.1 Update & get health profile
    res = client.put("/api/health/profile", json={
        "date_of_birth": "1995-05-15",
        "blood_group": "O+",
        "gender": "Female",
        "emergency_contact_name": "John Patient",
        "emergency_contact_phone": "+919876543210",
        "known_allergies": "Penicillin",
        "existing_conditions": "Mild asthma"
    }, headers=patient_headers)
    assert res.status_code == 200
    print("✅ Updated health profile")

    res = client.get("/api/health/profile", headers=patient_headers)
    assert res.status_code == 200
    profile = res.json()["profile"]
    assert profile["blood_group"] == "O+"
    assert profile["known_allergies"] == "Penicillin"
    print("✅ Retrieved health profile")

    # 2.2 Upload medical record (test file)
    sample_content = b"Patient: Alice Patient\nDate: 2026-10-30\nTest: Complete Blood Count\nHemoglobin: 13.5 g/dL (Normal)\nWBC: 7200 /mcL (Normal)\n"
    files = {"file": ("blood_test.pdf", sample_content, "application/pdf")}
    data = {"category": "Blood Test"}
    res = client.post("/api/health/records", files=files, data=data, headers=patient_headers)
    assert res.status_code == 200, f"Upload failed: {res.text}"
    record_id = res.json()["record_id"]
    print(f"✅ Uploaded health record (ID: {record_id})")

    # 2.3 List health records
    res = client.get("/api/health/records", headers=patient_headers)
    assert res.status_code == 200
    records = res.json()["records"]
    assert len(records) > 0
    assert any(r["id"] == record_id for r in records)
    print("✅ Health record listed in patient's documents")

    # 2.4 Download health record
    res = client.get(f"/api/health/records/{record_id}/download", headers=patient_headers)
    assert res.status_code == 200
    assert len(res.content) == len(sample_content)
    print("✅ Secure download of health record verified")

    # 2.5 AI Document Summarize
    res = client.post(f"/api/health/records/{record_id}/summarize", headers=patient_headers)
    assert res.status_code == 200, f"Summarize failed: {res.text}"
    summary_data = res.json()
    assert "summary" in summary_data or "message" in summary_data
    assert "disclaimer" in summary_data
    print("✅ AI Document Summarization returned valid structured analysis")

    # 2.6 Health Dashboard aggregation
    res = client.get("/api/health/dashboard", headers=patient_headers)
    assert res.status_code == 200
    dash = res.json()
    assert dash["total_records"] >= 1
    print(f"✅ Health Dashboard aggregated {dash['total_records']} records")

    # 2.7 Delete record
    res = client.delete(f"/api/health/records/{record_id}", headers=patient_headers)
    assert res.status_code == 200
    print("✅ Health record deleted")

    # ----------------------------------------------------
    # FEATURE 3: AI-Powered Medication Reminders
    # ----------------------------------------------------
    print("\n--- Testing Feature 3: Medication Reminders ---")
    # 3.1 AI Schedule calculation
    res = client.post("/api/reminders/ai-schedule", json={
        "medicine_name": "Amoxicillin",
        "frequency": "twice_daily",
        "instructions": "Take after meals"
    }, headers=patient_headers)
    assert res.status_code == 200
    sched = res.json()
    assert len(sched["times"]) == 2
    print(f"✅ AI Schedule generated dose times: {sched['times']}")

    # 3.2 Create medication reminder
    res = client.post("/api/reminders", json={
        "medicine_name": "Amoxicillin",
        "dosage": "500mg",
        "frequency": "twice_daily",
        "instructions": "Take after meals",
        "reminder_times": ["08:00", "20:00"]
    }, headers=patient_headers)
    assert res.status_code == 200
    med_id = res.json()["id"]
    print(f"✅ Created medication reminder (ID: {med_id})")

    # 3.3 List reminders
    res = client.get("/api/reminders", headers=patient_headers)
    assert res.status_code == 200
    meds = res.json()["medications"]
    assert any(m["id"] == med_id for m in meds)
    print("✅ Listed user's active medication reminders")

    # 3.4 Get due doses for today
    res = client.get("/api/reminders/due", headers=patient_headers)
    assert res.status_code == 200
    doses = res.json()["doses"]
    assert len(doses) >= 2
    dose = doses[0]
    print(f"✅ Found today's dose: {dose['medicine_name']} at {dose['reminder_time']} (status: {dose['status']})")

    # 3.5 Mark dose taken
    res = client.post(f"/api/reminders/{med_id}/taken", json={
        "scheduled_datetime": dose["scheduled_datetime"],
        "action": "taken"
    }, headers=patient_headers)
    assert res.status_code == 200
    print("✅ Recorded dose taken")

    # 3.6 Mark dose skipped
    dose2 = doses[1]
    res = client.post(f"/api/reminders/{med_id}/skip", json={
        "scheduled_datetime": dose2["scheduled_datetime"],
        "action": "skipped"
    }, headers=patient_headers)
    assert res.status_code == 200
    print("✅ Recorded dose skipped")

    # 3.7 Check adherence stats
    res = client.get("/api/reminders/adherence", headers=patient_headers)
    assert res.status_code == 200
    adh = res.json()
    assert adh["taken_count"] >= 1
    assert adh["skipped_count"] >= 1
    print(f"✅ Adherence compliance calculated: {adh['adherence_rate']}% (Taken: {adh['taken_count']}, Skipped: {adh['skipped_count']})")

    # 3.8 Pause & resume reminder
    res = client.put(f"/api/reminders/{med_id}/pause", headers=patient_headers)
    assert res.status_code == 200
    assert res.json()["is_paused"] is True
    res = client.put(f"/api/reminders/{med_id}/pause", headers=patient_headers)
    assert res.status_code == 200
    assert res.json()["is_paused"] is False
    print("✅ Toggled pause/resume reminder")

    # 3.9 Delete reminder
    res = client.delete(f"/api/reminders/{med_id}", headers=patient_headers)
    assert res.status_code == 200
    print("✅ Deleted medication reminder")

    print("\n========================================")
    print("🎉 ALL PLATFORM EXPANSION TESTS PASSED!")
    print("========================================")

if __name__ == "__main__":
    run_tests()
