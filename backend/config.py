"""
config.py
----------
Reads the Gemini API key and model name from environment variables (.env file).
This is the standard, GitHub-safe way to handle secrets: the key lives in a
.env file that is never committed to version control (see .gitignore).

We intentionally do NOT let the website write to this at runtime anymore -
writing files while uvicorn --reload is watching the folder was causing the
server to restart mid-request, which is what caused the "Something went
wrong" errors. Set your key in .env and restart the server once instead.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def get_gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()


def is_demo_mode() -> bool:
    key = get_gemini_key()
    return key in ("", "your_api_key_here")
