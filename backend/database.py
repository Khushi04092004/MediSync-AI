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

    conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row else None
