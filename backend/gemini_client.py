"""
gemini_client.py
-----------------
Talks to Gemini AI.

IMPORTANT (beginner-friendly):
If no API key is set in .env, this file runs in "DEMO MODE" and returns sample
responses - so you can test the whole website without needing a key yet.
Once a real key is added to .env (and the server is restarted), real Gemini
responses kick in automatically.

This file also raises clear, readable errors (instead of crashing silently)
if the API key is wrong, the model name is invalid, or Gemini's reply can't
be parsed - so the website can show you a helpful message instead of a
generic "Something went wrong".
"""

import json
import base64
import requests

import config

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "mr": "Marathi",
}


class GeminiError(Exception):
    """Raised whenever something goes wrong talking to Gemini, with a clear message."""
    pass


def _call_gemini(parts: list) -> str:
    api_key = config.get_gemini_key()
    model = config.get_gemini_model()
    url = GEMINI_URL_TEMPLATE.format(model=model)

    try:
        response = requests.post(
            f"{url}?key={api_key}",
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {"temperature": 0.3}
            },
            timeout=60,
        )
    except requests.exceptions.RequestException as e:
        raise GeminiError(f"Could not reach Gemini (network issue): {e}")

    if response.status_code == 400:
        raise GeminiError("Gemini rejected the request (400) - usually means the API key is invalid or malformed.")
    if response.status_code == 403:
        raise GeminiError("Gemini refused access (403) - check that your API key is correct and has Gemini API enabled.")
    if response.status_code == 404:
        raise GeminiError(f"Model '{model}' was not found (404) - it may have been renamed. "
                           f"Check available models at aistudio.google.com and update GEMINI_MODEL in .env.")
    if response.status_code == 429:
        raise GeminiError("Gemini rate limit / quota exceeded (429) - wait a moment and try again.")
    if not response.ok:
        raise GeminiError(f"Gemini returned an error ({response.status_code}): {response.text[:200]}")

    data = response.json()
    try:
        candidate = data["candidates"][0]
    except (KeyError, IndexError):
        # Common cause: the prompt was blocked by Gemini's safety filters
        reason = data.get("promptFeedback", {}).get("blockReason", "unknown")
        raise GeminiError(f"Gemini did not return a response (possibly blocked: {reason}).")

    try:
        return candidate["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise GeminiError("Gemini's response was in an unexpected format.")


def _extract_json(text: str) -> dict:
    """Gemini sometimes wraps JSON in ```json fences - strip them."""
    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        raise GeminiError("Gemini's reply wasn't valid JSON. Try again, or rephrase your input.")


def _lang_instruction(language: str) -> str:
    name = LANGUAGE_NAMES.get(language, "English")
    return f"\nRespond with all text values in {name}. Keep JSON keys in English exactly as specified."


# ---------------------------------------------------------------------------
# MODULE 1: Handwritten prescription -> extract medicines via Gemini Vision
# ---------------------------------------------------------------------------
def analyze_prescription_image(image_bytes: bytes, mime_type: str = "image/jpeg", language: str = "en") -> dict:
    if config.is_demo_mode():
        return {
            "demo_mode": True,
            "medicines": [
                {"name": "Amoxicillin", "dosage": "500mg", "frequency": "Twice a day", "duration": "5 days"},
                {"name": "Paracetamol", "dosage": "650mg", "frequency": "Thrice a day", "duration": "3 days"},
            ],
            "raw_confidence": 0.55,
            "note": "This is a DEMO response. Add a Gemini API key to .env for real AI Vision results."
        }

    prompt = """
You are a medical prescription reading assistant. Look at this handwritten prescription image.
Extract every medicine mentioned. Respond ONLY with valid JSON, no explanation, in this exact format:
{
  "medicines": [
    {"name": "...", "dosage": "...", "frequency": "...", "duration": "..."}
  ],
  "raw_confidence": 0.0 to 1.0 (how confident you are that the reading is accurate)
}
If you cannot read the handwriting clearly, set raw_confidence below 0.5.
Never invent a medicine name you are not reasonably confident about.
""" + _lang_instruction(language)

    parts = [
        {"text": prompt},
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}},
    ]
    text = _call_gemini(parts)
    result = _extract_json(text)
    result["demo_mode"] = False
    return result


# ---------------------------------------------------------------------------
# MODULE 1b: Digital prescription (already-extracted text) -> structure it
# ---------------------------------------------------------------------------
def parse_digital_prescription_text(raw_text: str, language: str = "en") -> dict:
    if config.is_demo_mode():
        return {
            "demo_mode": True,
            "medicines": [
                {"name": "Cetirizine", "dosage": "10mg", "frequency": "Once a day", "duration": "5 days"},
            ],
            "raw_confidence": 0.95,
            "note": "This is a DEMO response. Add a Gemini API key to .env for real results."
        }

    prompt = f"""
You are a medical prescription reading assistant. Below is text extracted from a digital PDF prescription.
Extract every medicine mentioned. Respond ONLY with valid JSON in this exact format:
{{
  "medicines": [
    {{"name": "...", "dosage": "...", "frequency": "...", "duration": "..."}}
  ],
  "raw_confidence": 0.0 to 1.0
}}

Prescription text:
\"\"\"{raw_text}\"\"\"
""" + _lang_instruction(language)

    text = _call_gemini([{"text": prompt}])
    result = _extract_json(text)
    result["demo_mode"] = False
    return result


# ---------------------------------------------------------------------------
# MODULE 2: Self-Care Assistant -> OTC-only recommendation
# ---------------------------------------------------------------------------
def get_otc_recommendation(symptoms: list, patient_info: dict, language: str = "en") -> dict:
    if config.is_demo_mode():
        return {
            "demo_mode": True,
            "recommendations": [
                {
                    "possible_cause": "Common viral fever / seasonal cold",
                    "medicine": "Paracetamol 500mg",
                    "dosage": "1 tablet after food, twice a day",
                    "precautions": "Avoid if allergic to Paracetamol. Do not exceed 4 tablets/day.",
                    "doctor_visit_required": "Only if fever continues beyond 3 days or exceeds 102°F"
                }
            ],
            "note": "This is a DEMO response. Add a Gemini API key to .env for real AI suggestions."
        }

    prompt = f"""
You are a cautious self-care assistant inside a pharmacy machine.
STRICT RULES (never break these):
1. You must ONLY suggest Over-the-Counter (OTC) medicines. NEVER suggest any prescription-only medicine.
2. If symptoms sound severe, unusual, or dangerous (e.g. chest pain, breathing difficulty, high fever in infants,
   pregnancy complications), do NOT suggest medicine - instead set doctor_visit_required to "Yes, immediately".
3. Consider the patient info given (age, weight, pregnancy, allergy, diabetes, blood pressure) before suggesting.
4. Respond ONLY with valid JSON, no explanation, in this exact format:
{{
  "recommendations": [
    {{
      "possible_cause": "...",
      "medicine": "...",
      "dosage": "...",
      "precautions": "...",
      "doctor_visit_required": "Yes / No / Yes, immediately - with short reason"
    }}
  ]
}}

Patient symptoms: {symptoms}
Patient info: {json.dumps(patient_info)}
""" + _lang_instruction(language)

    text = _call_gemini([{"text": prompt}])
    result = _extract_json(text)
    result["demo_mode"] = False
    return result


# ---------------------------------------------------------------------------
# MODULE 8: Chatbot - free-form conversation with a cautious health assistant
# ---------------------------------------------------------------------------
def chat_reply(history: list, message: str, language: str = "en") -> dict:
    """
    history = [{"role": "user"|"assistant", "content": "..."}]
    Returns {"reply": "...", "demo_mode": bool}
    """
    if config.is_demo_mode():
        return {
            "demo_mode": True,
            "reply": ("This is a DEMO reply (no Gemini key set in .env yet). "
                      "Once connected, I can chat about general health questions, explain how MediSync AI works, "
                      "and point you to the right module - but I'll never suggest prescription medicine or replace a doctor.")
        }

    system_prompt = f"""
You are the MediSync AI assistant chatbot embedded in a pharmacy website.
RULES (never break these):
1. You may discuss general health/wellness topics and explain how this website works.
2. NEVER name a specific prescription-only medicine or dosage as a recommendation.
   You may suggest OTC (over-the-counter) options only for very mild, common symptoms.
3. If the person describes anything serious, urgent, or unclear, tell them to consult a doctor or pharmacist,
   and mention the Self-Care Assistant or Scan Prescription modules on this site if relevant.
4. Keep answers short and conversational (2-5 sentences). Do not use markdown headers.
5. You are not a doctor and must not diagnose conditions.
""" + _lang_instruction(language)

    parts = [{"text": system_prompt}]
    for turn in history[-10:]:  # keep last 10 turns to stay within context limits
        role_label = "User" if turn["role"] == "user" else "Assistant"
        parts.append({"text": f"{role_label}: {turn['content']}"})
    parts.append({"text": f"User: {message}\nAssistant:"})

    reply_text = _call_gemini(parts)
    return {"demo_mode": False, "reply": reply_text.strip()}
