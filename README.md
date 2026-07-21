# 🏥 MediSync AI — AI-Powered Smart Pharmacy System

An AI-assisted prescription verification and dispensing system: scan a prescription (digital, handwritten, or QR), get safe OTC self-care suggestions, order medicine online, and manage inventory — all gated behind a safety-first verification pipeline where AI only ever *assists*, never makes the final call.

---

## 📁 Project Structure

```
medisync-ai/
├── backend/
│   ├── main.py                ← FastAPI server, all API routes
│   ├── database.py             ← SQLite schema + demo data
│   ├── auth.py                  ← login/signup, password hashing, sessions, roles
│   ├── gemini_client.py         ← Gemini AI calls (prescription reading, self-care, chatbot)
│   ├── verification.py          ← stock/expiry/prescription safety checks
│   ├── orders.py                 ← cart → payment → delivery tracking logic
│   ├── qr_decode.py               ← QR code decoding
│   ├── payment_gateway.py         ← Razorpay scaffold (optional, see below)
│   ├── delivery_provider.py       ← Shiprocket scaffold (optional, see below)
│   ├── config.py                   ← reads .env
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html, login.html, signup.html
│   ├── scan.html, selfcare.html, order.html, inventory.html, about.html
│   └── static/ (style.css, app.js, i18n.js)
├── render.yaml                 ← optional one-click Render.com deploy config
├── .gitignore
└── README.md
```

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
> **Why no `--reload`?** This app writes to `medisync.db` every time stock changes, an order is placed, etc. If `--reload` is on, uvicorn sees that file change and restarts the server mid-request — causing random "Something went wrong" errors. Only use `--reload` while you're actively editing the Python code yourself.

Open **http://127.0.0.1:8000** — you'll land on the Sign Up page.

---

## 🔐 Login / Signup — Step by Step

1. First visit → you're redirected to **signup.html**
2. Fill in name, email, password (6+ characters) → leave **Admin Code** blank → click Sign Up
3. You're logged in automatically and redirected to the home page
4. Next time, use **login.html** with the same email/password
5. Your name appears top-right → click it → "Log out" ends your session

**Passwords are hashed** (PBKDF2 + random salt per user) — never stored in plain text.

### Admin vs Customer accounts
- Every signup is a **customer** account by default (can scan prescriptions, use self-care, order medicine, dispense).
- To get an **admin** account (can add/edit/delete medicines in Inventory), you need an **Admin Code**. Set one yourself:
  1. In `backend/.env`, add: `ADMIN_SIGNUP_CODE=whatever-secret-you-want`
  2. Restart the server
  3. On the Signup page, enter that exact code in the "Admin Code" field
- If `ADMIN_SIGNUP_CODE` is left blank in `.env`, **nobody** can create an admin account — safest default.

---

## 🔑 Gemini API Key Setup — Step by Step (for real AI, not demo answers)

Right now the app runs in **DEMO MODE**: Scan Prescription, Self-Care, and the Chatbot all return realistic sample responses so you can test the whole app without any key. To switch on real Gemini AI:

1. Go to https://aistudio.google.com/app/apikey and sign in with a Google account
2. Click **"Create API key"** → copy it (starts with `AIza...`) — this is free
3. In `backend/`, find the file `.env.example`
4. Make a **copy** of it and rename the copy to exactly `.env` (no ".example")
5. Open `.env` in any text editor and replace this line:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
   with:
   ```
   GEMINI_API_KEY=AIzaSy...your_real_key...
   ```
6. Save the file
7. Stop the server (`Ctrl + C` in the terminal) and start it again:
   ```
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```
8. Go to the **About** page in the app — the pill next to "AI Settings" should now say **"✓ Connected to Gemini"** instead of "🧪 Demo Mode"

That's it — Scan Prescription, Self-Care, and the Chatbot will now use real Gemini responses.

**Why isn't there a "paste your key here" box in the website itself?** Because that would mean your secret key lives in your browser/database instead of a file that's excluded from Git — this `.env` approach is the standard, secure way real projects handle API keys, and it's what makes it safe to push this project to GitHub (see below).

---

## ❓ Will my README show up on GitHub for everyone to see?

**Yes — and that's completely normal.** Every public GitHub repository shows its `README.md` on the main page automatically; that's what it's *for* (explaining the project to visitors). There's nothing in this README that's sensitive — your actual secret (the Gemini key) lives only in your local `.env` file, which `.gitignore` stops from ever being uploaded. So it's safe to push this repo, README included, exactly as is.

---

## 🌐 Languages + 🌙 Dark Mode + 💬 Chatbot

- **5 languages**: English, हिंदी, বাংলা, தமிழ், मराठी — switch via the 🌐 icon top-right
- **Dark/Light mode**: toggle via the 🌙/☀️ icon, saved per-browser
- **Chatbot**: 💬 bubble bottom-right on every page — ask general health questions or "how does this app work"

---

## 📷 QR Code Scanning — Setup (optional but included)

QR decoding needs a system library called `zbar` in addition to the Python package (already in `requirements.txt`). If it's missing, the QR upload will show a clear error instead of crashing.

- **Mac**: `brew install zbar`
- **Ubuntu/Debian Linux**: `sudo apt-get install libzbar0`
- **Windows**: usually works out of the box with `pip install pyzbar`; if you get an error, install the [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) and try again

Tested by me (generated a QR code containing prescription text, uploaded it, confirmed it decodes correctly and feeds into the same AI parser as PDFs).

---

## 🧪 Testing Every Module

| Module | How to test |
|---|---|
| **Scan Prescription** | Try all 4 modes: PDF, handwritten photo, QR code, or pasted text |
| **Self-Care Assistant** | Pick symptoms + fill patient details → get an OTC-only suggestion |
| **Order Medicine Online** | Add items to cart → checkout → pick **COD** / **UPI** / **Card** → if your cart has a Prescription-category medicine, you'll be asked to upload a prescription first (AI cross-checks the name matches) |
| **Medicine Inventory** | Only **admin** accounts can add/edit/delete; any logged-in user can view |
| **About** | Shows safety rules, AI workflow, and your Gemini connection status |

---

## 💳 Real Payment Gateway (Razorpay) — optional, unverified by me

The tested, default payment flow is the simulated COD/UPI/Card logic (works out of the box, no setup). If you want **real** Razorpay payments:

1. Get test keys from https://dashboard.razorpay.com/app/keys
2. Add to `.env`: `RAZORPAY_KEY_ID=...` and `RAZORPAY_KEY_SECRET=...`
3. See `backend/payment_gateway.py` — it has working functions to create a real Razorpay order and verify its signature, following Razorpay's documented API.

**Honesty note**: I don't have a real Razorpay account, so I could not test this end-to-end — the code follows their published API shape correctly, but you should test it yourself with Razorpay's TEST MODE before trusting it with real transactions. It is not wired into the live checkout flow (to avoid breaking the tested COD/UPI/Card path) — you'd connect `place_order()` in `main.py` to call `payment_gateway.create_razorpay_order()` for the UPI/Card cases.

## 🚚 Real Courier Integration (Shiprocket) — optional, unverified by me

Same situation: the tested default is simulated tracking (Placed → Verified → Packed → Out for Delivery → Delivered). For real Shiprocket booking, see `backend/delivery_provider.py` and add `SHIPROCKET_EMAIL` / `SHIPROCKET_PASSWORD` to `.env`. I don't have a Shiprocket business account to test this against, so treat it as a starting scaffold, not verified working code.

---

## ☁️ Deploying Online (so anyone can access it, not just your computer)

1. Push this project to GitHub (see below)
2. Go to https://render.com → sign up (free) → "New +" → "Blueprint"
3. Connect your GitHub repo — Render reads `render.yaml` automatically and sets everything up
4. In Render's dashboard, add your `GEMINI_API_KEY` (and `ADMIN_SIGNUP_CODE` if you want one) as environment variables — these aren't in the repo, so you add them directly on Render
5. Deploy — you'll get a public URL like `https://medisync-ai.onrender.com`

**Limitation to know about**: Render's free tier has an *ephemeral* filesystem — your `medisync.db` (all medicines, orders, and user accounts) resets on every restart/redeploy. Fine for showing off a demo; for anything persistent, add Render's paid Disk add-on or migrate to a hosted database.

---

## 🐙 Pushing to GitHub

```
cd medisync-ai
git init
git add .
git commit -m "MediSync AI: AI-powered smart pharmacy system"
git remote add origin https://github.com/your-username/medisync-ai.git
git branch -M main
git push -u origin main
```

`.gitignore` (already included) keeps `venv/`, `*.db`, and `.env` out of the repo — so your Gemini key and local data never get uploaded.

---

## 🛠 Troubleshooting

| Problem | Solution |
|---|---|
| Blank white page on login/signup | Fixed in this version — if you still see it, make sure you extracted this exact zip and didn't mix in old files |
| "Something went wrong" repeatedly | Make sure you're **not** using `--reload` when running the server |
| 401 errors on every action | Your session expired (7 days) or you're not logged in — go to login.html |
| QR upload fails with a library error | See the QR Code Scanning section above for your OS |
| Admin Code doesn't work | Check `ADMIN_SIGNUP_CODE` is set in `.env` and matches exactly, then restart the server |
| Database has stale/duplicate data | Delete `backend/medisync.db` and restart — it reseeds automatically |

---

## 🚀 What's Left for the Future

- Real Razorpay/Shiprocket credentials plugged in and tested by you
- Email verification on signup
- Rate limiting on login attempts
- Migrating from SQLite to a hosted database for production use

Enjoy building on this — and good luck with your submission! 💪
