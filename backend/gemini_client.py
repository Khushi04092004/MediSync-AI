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


# ---------------------------------------------------------------------------
# MODULE 9: Health Document Summarization (Feature 2)
# ---------------------------------------------------------------------------
def summarize_health_document_text(text: str, language: str = "en") -> dict:
    if config.is_demo_mode():
        return {
            "document_type": "Medical Report (Demo)",
            "patient_name": "Sample Patient",
            "report_date": "Recent",
            "key_findings": [
                {"parameter": "Hemoglobin", "value": "13.2 g/dL", "status": "Normal"},
                {"parameter": "Total Leukocyte Count", "value": "6,800 /mcL", "status": "Normal"},
                {"parameter": "Platelet Count", "value": "250,000 /mcL", "status": "Normal"},
                {"parameter": "Fasting Blood Glucose", "value": "92 mg/dL", "status": "Normal"}
            ],
            "doctor_notes": "All reported blood parameters are within standard physiological reference ranges. No indicators of acute infection or anemia detected.",
            "recommendations": [
                "Maintain healthy diet and hydration",
                "Share this report with your physician during your next routine consultation"
            ],
            "important_alerts": []
        }

    prompt = f"""
You are an expert medical report analysis assistant in a health platform.
Analyze the following extracted text from a patient's medical document or lab report.

STRICT INSTRUCTIONS:
1. Explain findings in simple, easy-to-understand language that a patient can comprehend.
2. Group key test parameters/vitals into 'key_findings' with parameter, value, and status ('Normal', 'Low', 'High', 'Abnormal', 'Attention').
3. In 'doctor_notes', write a friendly 2-4 sentence summary of what the report means.
4. Highlight any urgent or abnormal findings in 'important_alerts'.
5. Provide actionable next steps or questions to ask the doctor in 'recommendations'.
6. Respond ONLY with valid JSON in this exact structure:
{{
  "document_type": "...",
  "patient_name": "...",
  "report_date": "...",
  "key_findings": [
    {{"parameter": "...", "value": "...", "status": "Normal|Low|High|Abnormal|Attention"}}
  ],
  "doctor_notes": "...",
  "recommendations": ["..."],
  "important_alerts": ["..."]
}}

Document Text:
{text[:4000]}
""" + _lang_instruction(language)

    response_text = _call_gemini([{"text": prompt}])
    return _extract_json(response_text)


def summarize_health_document_image(image_bytes: bytes, mime_type: str = "image/jpeg", language: str = "en") -> dict:
    if config.is_demo_mode():
        return summarize_health_document_text("", language)

    prompt = f"""
You are an expert medical report analysis assistant in a health platform.
Analyze this medical document / prescription / lab test image.

STRICT INSTRUCTIONS:
1. Read the text from the image carefully.
2. Explain findings in simple, easy-to-understand language.
3. Group key test parameters or findings into 'key_findings' with parameter, value, and status ('Normal', 'Low', 'High', 'Abnormal', 'Attention').
4. In 'doctor_notes', write a 2-4 sentence patient-friendly summary.
5. Highlight any abnormal or urgent findings in 'important_alerts'.
6. Provide actionable recommendations or questions to ask the doctor in 'recommendations'.
7. Respond ONLY with valid JSON in this exact structure:
{{
  "document_type": "...",
  "patient_name": "...",
  "report_date": "...",
  "key_findings": [
    {{"parameter": "...", "value": "...", "status": "Normal|Low|High|Abnormal|Attention"}}
  ],
  "doctor_notes": "...",
  "recommendations": ["..."],
  "important_alerts": ["..."]
}}
""" + _lang_instruction(language)

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    parts = [
        {"inlineData": {"mimeType": mime_type, "data": encoded_image}},
        {"text": prompt}
    ]
    response_text = _call_gemini(parts)
    return _extract_json(response_text)


# ---------------------------------------------------------------------------
# MODULE 10: AI-Powered Medication Reminder Scheduling (Feature 3)
# ---------------------------------------------------------------------------
def generate_reminder_schedule(medicine_name: str, frequency: str, instructions: str = "",
                               wake_time: str = "08:00", sleep_time: str = "22:00") -> dict:
    default_times = {
        "once_daily": ["09:00"],
        "twice_daily": ["09:00", "21:00"],
        "thrice_daily": ["08:00", "14:00", "20:00"],
        "four_times_daily": ["08:00", "12:00", "16:00", "20:00"],
        "as_needed": ["10:00"]
    }
    fallback_times = default_times.get(frequency, ["09:00"])

    if config.is_demo_mode():
        return {
            "demo_mode": True,
            "times": fallback_times,
            "explanation": f"Standard schedule for {frequency.replace('_', ' ')} based on routine daytime hours.",
            "tips": [
                "Take with a full glass of water",
                "Try to take at the same times each day for optimal adherence"
            ]
        }

    prompt = f"""
You are a smart clinical pharmacy assistant optimizing medication intake timing.
Given a medicine name, prescribed frequency, and optional instructions, calculate the most effective and patient-friendly daily reminder times (24-hour format HH:MM).

Inputs:
- Medicine: {medicine_name}
- Prescribed Frequency: {frequency}
- Patient Instructions: {instructions or 'None specified'}
- Patient Wake Time: {wake_time}
- Patient Bed Time: {sleep_time}

Rules:
1. Ensure doses are evenly spaced between wake time and bed time unless food-specific (e.g., before breakfast, after dinner).
2. 'times' MUST be an array of "HH:MM" 24-hour time strings corresponding to the frequency count.
   - once_daily: 1 time
   - twice_daily: 2 times
   - thrice_daily: 3 times
   - four_times_daily: 4 times
   - as_needed: 1 recommended default time
3. Provide a brief 1-2 sentence 'explanation' of why these times are optimal.
4. Provide 2-3 helpful 'tips' for taking this medication.
5. Respond ONLY with valid JSON:
{{
  "times": ["08:00", "20:00"],
  "explanation": "...",
  "tips": ["...", "..."]
}}
"""
    try:
        response_text = _call_gemini([{"text": prompt}])
        result = _extract_json(response_text)
        if "times" not in result or not isinstance(result["times"], list) or len(result["times"]) == 0:
            result["times"] = fallback_times
        result["demo_mode"] = False
        return result
    except Exception:
        return {
            "demo_mode": False,
            "times": fallback_times,
            "explanation": f"Recommended schedule for {frequency.replace('_', ' ')}.",
            "tips": ["Take with a full glass of water", "Keep doses evenly spaced"]
        }

