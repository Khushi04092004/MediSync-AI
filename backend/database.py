"""
database.py
------------
Creates the SQLite database and defines the schema for medicines and orders.
SQLite is a file-based database - no separate server needs to be installed.
The database file is created automatically as 'medisync.db' in the backend folder.
"""

import sqlite3
import os
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "medisync.db")


def get_connection():
    """Every API call gets a connection through this function."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access rows like dictionaries
    return conn


def _column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def init_db():
    """Creates tables if they don't exist, migrates old databases, and seeds demo data."""
    conn = get_connection()
    cur = conn.cursor()

    # -----------------------------------------------------------------------
    # EXPANSION: Doctor Appointment Booking, Health Records, Medication Reminders
    # New tables are created with CREATE TABLE IF NOT EXISTS — safe for
    # existing databases. No existing tables are modified or dropped.
    # -----------------------------------------------------------------------

    # Feature 1: Doctor profiles (linked to users table via user_id)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            specialization TEXT NOT NULL,
            qualifications TEXT NOT NULL DEFAULT '',
            experience_years INTEGER NOT NULL DEFAULT 0,
            consultation_fee REAL NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT '',
            profile_image_url TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Feature 1: Doctor availability slots
    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctor_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER NOT NULL,
            available_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            max_slots INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)

    # Feature 1: Appointments between patients and doctors
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_uid TEXT NOT NULL UNIQUE,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            availability_id INTEGER,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES users(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)

    # Feature 2: Extended patient health profile
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patient_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            date_of_birth TEXT NOT NULL DEFAULT '',
            blood_group TEXT NOT NULL DEFAULT '',
            gender TEXT NOT NULL DEFAULT '',
            emergency_contact_name TEXT NOT NULL DEFAULT '',
            emergency_contact_phone TEXT NOT NULL DEFAULT '',
            known_allergies TEXT NOT NULL DEFAULT '',
            existing_conditions TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Feature 2: Health record file uploads
    cur.execute("""
        CREATE TABLE IF NOT EXISTS health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'General',
            file_size INTEGER NOT NULL DEFAULT 0,
            mime_type TEXT NOT NULL DEFAULT '',
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Feature 3: Medication reminder definitions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            medicine_name TEXT NOT NULL,
            dosage TEXT NOT NULL DEFAULT '',
            frequency TEXT NOT NULL DEFAULT 'once_daily',
            instructions TEXT NOT NULL DEFAULT '',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_paused INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Feature 3: Individual reminder time entries per medication
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medication_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL,
            reminder_time TEXT NOT NULL,
            FOREIGN KEY (medication_id) REFERENCES medications(id)
        )
    """)

    # Feature 3: Medication adherence log (taken / skipped)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medication_adherence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            scheduled_datetime TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'pending',
            logged_at TEXT,
            FOREIGN KEY (medication_id) REFERENCES medications(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # -----------------------------------------------------------------------
    # End of expansion tables
    # -----------------------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            generic_name TEXT,
            brand TEXT,
            strength TEXT,
            category TEXT,
            otc_or_prescription TEXT NOT NULL,  -- 'OTC' or 'Prescription'
            stock INTEGER NOT NULL DEFAULT 0,
            drawer_number TEXT,
            expiry_date TEXT,
            price REAL NOT NULL DEFAULT 0
        )
    """)

    # Migration safety net: if an older medisync.db already exists without
    # the price column, add it instead of crashing.
    if not _column_exists(cur, "medicines", "price"):
        cur.execute("ALTER TABLE medicines ADD COLUMN price REAL NOT NULL DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            items_json TEXT NOT NULL,
            total_amount REAL NOT NULL,
            address TEXT NOT NULL,
            payment_status TEXT NOT NULL DEFAULT 'Pending',
            order_status TEXT NOT NULL DEFAULT 'Placed',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer',
            created_at TEXT NOT NULL
        )
    """)
    if not _column_exists(cur, "users", "role"):
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'customer'")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)

    conn.commit()

    # Seed demo medicines only if the table is empty (avoids duplicates on restart)
    cur.execute("SELECT COUNT(*) FROM medicines")
    count = cur.fetchone()[0]

    if count == 0:
        today = date.today()
        far_future = (today + timedelta(days=400)).isoformat()
        near_future = (today + timedelta(days=20)).isoformat()
        expired_date = (today - timedelta(days=10)).isoformat()

        demo_medicines = [
            # name, generic_name, brand, strength, category, otc/prescription, stock, drawer, expiry, price(INR)
            ("Paracetamol", "Paracetamol", "Crocin", "500mg", "Pain Relief / Fever", "OTC", 120, "A1", far_future, 25),
            ("Cetirizine", "Cetirizine", "Cetzine", "10mg", "Allergy / Cold", "OTC", 80, "A2", far_future, 30),
            ("ORS Powder", "Oral Rehydration Salts", "Electral", "21g sachet", "Rehydration", "OTC", 50, "A3", far_future, 20),
            ("Domperidone", "Domperidone", "Domstal", "10mg", "Vomiting / Nausea", "OTC", 60, "A4", near_future, 35),
            ("Ibuprofen", "Ibuprofen", "Brufen", "400mg", "Pain Relief", "OTC", 5, "A5", far_future, 40),
            ("ORS + Zinc", "ORS with Zinc", "Zincovit-ORS", "20g sachet", "Rehydration", "OTC", 40, "A6", far_future, 45),
            ("Antacid Gel", "Aluminium Hydroxide", "Digene", "170ml", "Acidity", "OTC", 30, "A7", far_future, 90),
            ("Amoxicillin", "Amoxicillin", "Novamox", "500mg", "Antibiotic", "Prescription", 100, "B1", far_future, 110),
            ("Amlodipine", "Amlodipine", "Amlodac", "5mg", "Blood Pressure", "Prescription", 70, "B2", far_future, 60),
            ("Metformin", "Metformin", "Glycomet", "500mg", "Diabetes", "Prescription", 90, "B3", far_future, 55),
            ("Azithromycin", "Azithromycin", "Azithral", "500mg", "Antibiotic", "Prescription", 0, "B4", far_future, 130),
            ("Expired Cough Syrup", "Dextromethorphan", "Old Cough Syrup", "100ml", "Cold / Cough", "OTC", 15, "A8", expired_date, 85),
        ]

        cur.executemany("""
            INSERT INTO medicines
            (name, generic_name, brand, strength, category, otc_or_prescription, stock, drawer_number, expiry_date, price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, demo_medicines)

        conn.commit()
        print(f"[database.py] Seeded {len(demo_medicines)} demo medicines.")

    # Seed demo doctors only if the doctors table is empty
    cur.execute("SELECT COUNT(*) FROM doctors")
    doc_count = cur.fetchone()[0]

    if doc_count == 0:
        _seed_demo_doctors(conn, cur)

    conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row else None


def _seed_demo_doctors(conn, cur):
    """Seeds demo doctor users and profiles. Called only when doctors table is empty."""
    import hashlib, secrets
    from datetime import datetime, timedelta, date

    today = date.today()
    now = datetime.now().isoformat()

    # Demo doctor data: (name, email, specialization, qualifications, experience_years, fee, description)
    demo_doctors_data = [
        ("Dr. Priya Sharma", "dr.priya@medisync.demo", "General Physician",
         "MBBS, MD (Internal Medicine)", 12, 500,
         "Experienced general physician specializing in preventive care, fever, infections, and chronic disease management."),
        ("Dr. Arjun Mehta", "dr.arjun@medisync.demo", "Cardiologist",
         "MBBS, MD, DM (Cardiology)", 18, 1200,
         "Senior cardiologist with expertise in heart disease, hypertension, and cardiac imaging."),
        ("Dr. Sneha Patel", "dr.sneha@medisync.demo", "Dermatologist",
         "MBBS, MD (Dermatology)", 8, 800,
         "Dermatologist treating skin conditions, acne, eczema, psoriasis, and cosmetic dermatology."),
        ("Dr. Rajiv Kumar", "dr.rajiv@medisync.demo", "Orthopedic Surgeon",
         "MBBS, MS (Orthopaedics)", 15, 1000,
         "Orthopedic specialist for bone, joint, and sports injuries including knee and spine conditions."),
        ("Dr. Anita Desai", "dr.anita@medisync.demo", "Gynecologist",
         "MBBS, MD, DGO (Obstetrics & Gynaecology)", 20, 900,
         "Experienced gynecologist offering prenatal care, fertility consultation, and women's health services."),
        ("Dr. Vikram Nair", "dr.vikram@medisync.demo", "Pediatrician",
         "MBBS, MD (Pediatrics)", 10, 700,
         "Pediatrician providing child healthcare from newborn to adolescence, including vaccinations."),
    ]

    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac("sha256", "Demo@1234".encode(), salt.encode(), 100_000).hex()

    inserted_doctor_user_ids = []
    for name, email, spec, quals, exp, fee, desc in demo_doctors_data:
        try:
            cur.execute(
                "INSERT INTO users (name, email, password_hash, password_salt, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, email, password_hash, salt, "doctor", now),
            )
            inserted_doctor_user_ids.append((cur.lastrowid, spec, quals, exp, fee, desc))
        except Exception:
            # Skip if this demo email already exists
            pass

    conn.commit()

    # Create doctor profiles for newly inserted demo users
    for user_id, spec, quals, exp, fee, desc in inserted_doctor_user_ids:
        cur.execute("""
            INSERT INTO doctors (user_id, specialization, qualifications, experience_years, consultation_fee, description, profile_image_url, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (user_id, spec, quals, exp, fee, desc, "", now))

    conn.commit()

    # Seed availability for the next 7 days for each doctor
    cur.execute("SELECT id FROM doctors")
    doctor_rows = cur.fetchall()
    time_slots = [
        ("09:00", "09:30"), ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00"),
        ("11:00", "11:30"), ("14:00", "14:30"), ("14:30", "15:00"), ("15:00", "15:30"),
        ("15:30", "16:00"), ("16:00", "16:30"),
    ]
    for row in doctor_rows:
        doc_id = row[0]
        for day_offset in range(1, 8):
            avail_date = (today + timedelta(days=day_offset)).isoformat()
            # Each doctor available 5 of the 10 slots alternating
            for i, (start, end) in enumerate(time_slots):
                if (doc_id + i) % 2 == 0:  # alternate slots
                    cur.execute("""
                        INSERT INTO doctor_availability (doctor_id, available_date, start_time, end_time, max_slots, is_active)
                        VALUES (?, ?, ?, ?, 1, 1)
                    """, (doc_id, avail_date, start, end))

    conn.commit()
    print(f"[database.py] Seeded {len(demo_doctors_data)} demo doctors with availability.")
