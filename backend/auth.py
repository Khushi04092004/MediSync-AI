"""
auth.py
--------
Simple username/password authentication for MediSync AI.

How it works:
  - Passwords are hashed with PBKDF2 (salted) - never stored in plain text.
  - On signup/login, a random session token is created and stored in the
    'sessions' table with an expiry date.
  - The frontend saves this token in localStorage and sends it as
    "Authorization: Bearer <token>" on every API call.
  - require_auth() is a FastAPI dependency that checks this token and blocks
    the request (401) if it's missing, invalid, or expired.

Note: this is solid for a personal/portfolio project, but a production app
would add things like email verification, rate limiting, and HTTPS-only
cookies instead of localStorage tokens.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Header, HTTPException

from database import get_connection, row_to_dict

SESSION_DURATION_DAYS = 7
ADMIN_SIGNUP_CODE = os.getenv("ADMIN_SIGNUP_CODE", "").strip()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def create_user(name: str, email: str, password: str, admin_code: str = "") -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,))
    if cur.fetchone():
        conn.close()
        raise ValueError("An account with this email already exists.")

    # An admin account is only created if the correct ADMIN_SIGNUP_CODE (set in .env) is provided.
    # Without it (or if ADMIN_SIGNUP_CODE isn't set in .env at all), every signup is a regular customer.
    role = "admin" if (ADMIN_SIGNUP_CODE and admin_code == ADMIN_SIGNUP_CODE) else "customer"

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    cur.execute(
        "INSERT INTO users (name, email, password_hash, password_salt, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, email, password_hash, salt, role, datetime.now().isoformat()),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "name": name, "email": email, "role": role}


def verify_user(email: str, password: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise ValueError("No account found with this email.")

    user = row_to_dict(row)
    if _hash_password(password, user["password_salt"]) != user["password_hash"]:
        raise ValueError("Incorrect password.")

    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}


def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    expires_at = (datetime.now() + timedelta(days=SESSION_DURATION_DAYS)).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expires_at))
    conn.commit()
    conn.close()
    return token


def get_user_from_token(token: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE token = ?", (token,))
    session_row = cur.fetchone()
    if session_row is None:
        conn.close()
        return None

    session = row_to_dict(session_row)
    if datetime.fromisoformat(session["expires_at"]) < datetime.now():
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return None

    cur.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user_row = cur.fetchone()
    conn.close()
    if user_row is None:
        return None
    user = row_to_dict(user_row)
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}


def delete_session(token: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def require_auth(authorization: str = Header(None)) -> dict:
    """FastAPI dependency: raises 401 if the request has no valid session token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    token = authorization.replace("Bearer ", "").strip()
    user = get_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    return user


def require_admin(authorization: str = Header(None)) -> dict:
    """FastAPI dependency: like require_auth, but also requires the 'admin' role."""
    current_user = require_auth(authorization)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="This action requires an admin account.")
    return current_user
