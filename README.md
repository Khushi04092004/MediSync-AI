# 🏥 MediSync AI — AI-Powered Smart Pharmacy System

An AI-assisted prescription verification and dispensing system: scan a prescription (digital, handwritten, or QR), get safe OTC self-care suggestions, order medicine online, and manage inventory — all gated behind a safety-first verification pipeline where AI only ever *assists*, never makes the final call.

---

## ✅ Setup (Step by Step)

### 1. Install Python
```
python3 --version
```
Need 3.9+. Get it at https://www.python.org/downloads/ if missing (tick "Add Python to PATH" on Windows).

### 2. Go to the backend folder
```
cd medisync-ai/backend
```

### 3. Create a virtual environment
```
python3 -m venv venv
```
Activate it:
- Mac/Linux: `source venv/bin/activate`
- Windows: `venv\Scripts\activate`

### 4. Install dependencies
```
pip install -r requirements.txt
```

### 5. Run the server (⚠️ without `--reload` for normal use)
```
uvicorn main:app --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000** — you'll land on the Sign Up page.

---
