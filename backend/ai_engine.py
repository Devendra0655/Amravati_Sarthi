import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from groq import AsyncGroq
from backend.database import get_government_schemes, get_nearby_businesses

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)

MOCK_AI = os.getenv("MOCK_AI", "false").strip().lower() in ("true", "1", "yes")
_client = None if MOCK_AI else AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
_MODEL  = "llama-3.3-70b-versatile"

# ── Keyword lists ─────────────────────────────────────────────────────────────
_LOCATION_KW = [
    "जवळचे", "जवळील", "जवळ", "कुठे", "कुठे आहे", "दवाखाना",
    "हॉस्पिटल", "रुग्णालय", "औषध", "फार्मसी",
    "near me", "nearby", "nearest", "closest", "close to me",
    "where is", "find", "locate", "show me", "directions to",
    "hospital near", "pharmacy near", "restaurant near",
    "atm near", "bank near", "clinic near",
]

_SCHEME_KW = [
    "योजना", "scheme", "yojana", "सरकारी", "government", "apply",
    "अर्ज", "eligibility", "पात्रता", "documents", "कागदपत्रे",
    "pm-kisan", "pm kisan", "ladki bahin", "लाडकी बहीण",
    "ayushman", "आयुष्मान", "ration", "रेशन", "pmay", "pmfby",
    "pension", "निवृत्तिवेतन", "scholarship", "शिष्यवृत्ती",
    "vishwakarma", "shetkari", "namo", "kisan credit",
]

_EMERGENCY_KW = [
    "emergency", "आपत्कालीन", "ambulance", "रुग्णवाहिका",
    "fire brigade", "अग्निशमन", "helpline", "हेल्पलाइन",
    "emergency number", "आपत्कालीन क्रमांक",
]

_CATEGORY_MAP = {
    "hospital":   ["hospital", "हॉस्पिटल", "दवाखाना", "रुग्णालय", "doctor", "डॉक्टर"],
    "pharmacy":   ["pharmacy", "medicine", "औषध", "medical shop", "फार्मसी", "medical"],
    "restaurant": ["restaurant", "food", "biryani", "जेवण", "खाणे", "रेस्टॉरंट", "dhaba", "cafe"],
    "hotel":      ["hotel", "हॉटेल", "lodge", "stay", "lodging", "लॉज"],
    "atm":        ["atm", "cash", "पैसे", "withdraw"],
    "bank":       ["bank", "बँक", "banking"],
    "clinic":     ["clinic", "क्लिनिक", "dispensary"],
    "college":    ["college", "कॉलेज", "university", "विद्यालय", "school"],
    "police":     ["police", "पोलीस", "thana", "ठाणे", "station"],
}

# ── Emergency data (hardcoded, instant) ───────────────────────────────────────
_EMERGENCY = {
    "en": (
        "🚨 Emergency Contacts — Amravati\n\n"
        "• Police: 100 | Amravati Control Room: 0721-2662100\n"
        "• Ambulance: 108 (Free, 24×7)\n"
        "• Fire Brigade: 101 | Amravati: 0721-2570101\n"
        "• Women Helpline: 1091\n"
        "• Child Helpline: 1098\n"
        "• Disaster Management: 1070\n"
        "• Civil Hospital Amravati: 0721-2662100\n"
        "• All Emergency Services: 112"
    ),
    "mr": (
        "🚨 आपत्कालीन संपर्क — अमरावती\n\n"
        "• पोलीस: 100 | अमरावती नियंत्रण कक्ष: 0721-2662100\n"
        "• रुग्णवाहिका: 108 (मोफत, 24×7)\n"
        "• अग्निशमन: 101 | अमरावती: 0721-2570101\n"
        "• महिला हेल्पलाइन: 1091\n"
        "• बाल हेल्पलाइन: 1098\n"
        "• आपत्ती व्यवस्थापन: 1070\n"
        "• शासकीय रुग्णालय अमरावती: 0721-2662100\n"
        "• सर्व आपत्कालीन सेवा: 112"
    ),
}

# ── System prompts ────────────────────────────────────────────────────────────
_LANG_RULE = {
    "en": (
        "MANDATORY LANGUAGE RULE: Your entire response must be in grammatically correct, "
        "clear English only. Do not use any Marathi words or Devanagari script. "
        "Use simple, accessible language that any citizen can understand."
    ),
    "mr": (
        "अनिवार्य भाषा नियम: तुमचे संपूर्ण उत्तर केवळ शुद्ध, व्याकरणदृष्ट्या अचूक मराठीत असावे. "
        "कोणतेही इंग्रजी शब्द किंवा वाक्ये वापरू नका. "
        "प्रत्येक नागरिकाला सहज समजेल अशा साध्या मराठी भाषेत उत्तर द्या."
    ),
}

_SYSTEM_MAIN = """\
You are "Amravati Sarthi" (अमरावती सारथी), a highly knowledgeable AI assistant \
dedicated to the citizens of Amravati, Maharashtra, India.

YOUR CAPABILITIES:
- Deep expertise in all central and state government welfare schemes: PM-KISAN, \
Ladki Bahin Yojana, Ayushman Bharat PM-JAY, PMAY (Gramin & Urban), PMFBY crop insurance, \
Ration Card, Namo Shetkari Maha Samman, Kisan Credit Card, PM Vishwakarma, \
Shubh Matrutva Yojana, and many others
- Complete knowledge of Amravati district: geography, culture, civic services, \
government offices, hospitals, educational institutions, local economy
- Agriculture support for Vidarbha farmers: crop insurance, soil health, market prices
- General knowledge: answer any question a citizen might ask — history, science, \
health advice, legal basics, education, career guidance
- Step-by-step guidance for government processes, applications, documentation

STRICT QUALITY STANDARDS:
1. Give specific, detailed, actionable answers — never vague or one-line responses
2. For scheme queries: always include eligibility criteria, exact documents required, \
   where and how to apply, processing timeline, and benefit amount
3. For general queries: answer completely as a knowledgeable expert would
4. Structure complex answers with clear bullet points and sections
5. Use exact figures: amounts (e.g., "Rs. 6,000 per year in 3 instalments of Rs. 2,000 each"), \
   dates, percentages — be precise
6. Proofread your response for grammar and spelling before outputting
7. If the database context provided is relevant, incorporate it accurately

{lang_rule}"""

_SYSTEM_LOC = """\
You are "Amravati Sarthi", a smart city assistant for Amravati, Maharashtra.
The user is searching for nearby services. Real business data is provided below.
Write a natural, helpful 1-2 sentence summary: state how many results were found \
and mention the name and distance of the closest one. Be warm and friendly.
The UI shows full details — do not list all results.

{lang_rule}"""

_MOCK_BIZ = [
    {"name": "Amravati Civil Hospital",  "category": "hospital",  "address": "Rajapeth, Amravati",        "lat": 20.9374, "lng": 77.7596, "phone": "0721-2662100",   "opening_hours": "24/7",        "distance_km": 0.8},
    {"name": "Shri Medicals & Pharmacy", "category": "pharmacy",  "address": "Badnera Road, Amravati",    "lat": 20.9310, "lng": 77.7540, "phone": "+91-9876543210", "opening_hours": "08:00-22:00", "distance_km": 1.2},
    {"name": "City Care Clinic",         "category": "clinic",    "address": "Jaistambh Chowk, Amravati", "lat": 20.9325, "lng": 77.7558, "phone": "+91-9823100001", "opening_hours": "09:00-21:00", "distance_km": 1.5},
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _matches(msg: str, kws: list) -> bool:
    ml = msg.lower()
    return any(k.lower() in ml for k in kws)

def _category_hint(msg: str) -> str:
    ml = msg.lower()
    for cat, kws in _CATEGORY_MAP.items():
        if any(k in ml for k in kws):
            return cat
    return ""

def _sys(template: str, lang: str) -> str:
    return template.format(lang_rule=_LANG_RULE.get(lang, _LANG_RULE["en"]))

async def _llm(system: str, user: str, max_tokens: int = 1200) -> str:
    resp = await _client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.6,
    )
    return resp.choices[0].message.content.strip()


# ── Mock ──────────────────────────────────────────────────────────────────────
async def _mock(msg: str, lang: str) -> str:
    await asyncio.sleep(1.0)
    if _matches(msg, _EMERGENCY_KW):
        return _EMERGENCY.get(lang, _EMERGENCY["en"])
    if _matches(msg, _LOCATION_KW):
        txt = (
            "मला तुमच्या जवळ 3 ठिकाणे सापडली. सर्वात जवळचे Amravati Civil Hospital आहे, फक्त 0.8 km अंतरावर."
            if lang == "mr" else
            "I found 3 nearby results for you. The closest is Amravati Civil Hospital, just 0.8 km away."
        )
        return f"LOCATIONS:{json.dumps(_MOCK_BIZ, ensure_ascii=False)}||{txt}"
    return (
        "नमस्कार! मी अमरावती सारथी आहे. सरकारी योजना, जवळचे रुग्णालय किंवा कोणत्याही नागरी सेवेबद्दल विचारा!"
        if lang == "mr" else
        "Hello! I'm Amravati Sarthi. Ask me about government schemes, nearby services, or anything about Amravati!"
    )


# ── Main ──────────────────────────────────────────────────────────────────────
async def process_chat_message(
    user_message: str,
    user_lat: float = 0.0,
    user_lng: float = 0.0,
    lang: str = "en",
) -> str:
    if MOCK_AI:
        return await _mock(user_message, lang)

    # Emergency — instant, no LLM needed
    if _matches(user_message, _EMERGENCY_KW):
        return _EMERGENCY.get(lang, _EMERGENCY["en"])

    # Location query
    if user_lat != 0.0 and user_lng != 0.0 and _matches(user_message, _LOCATION_KW):
        hint       = _category_hint(user_message) or user_message
        businesses = await get_nearby_businesses(hint, user_lat, user_lng)
        if not businesses:
            return (
                "मला जवळपास कोणतेही परिणाम सापडले नाहीत. कृपया वेगळ्या शब्दात शोधा."
                if lang == "mr" else
                "No results found nearby. Please try a different search term."
            )
        context = "\n\n".join(
            f"Name: {b['name']}\nCategory: {b['category']}\n"
            f"Address: {b['address']}\nDistance: {b['distance_km']} km\n"
            f"Phone: {b['phone'] or 'N/A'}\nHours: {b['opening_hours'] or 'N/A'}"
            for b in businesses
        )
        summary = await _llm(
            system=_sys(_SYSTEM_LOC, lang),
            user=f"User asked: {user_message}\n\nNearby results ({len(businesses)} found):\n{context}",
            max_tokens=160,
        )
        return f"LOCATIONS:{json.dumps(businesses, ensure_ascii=False)}||{summary}"

    # Scheme or general query — fetch optional DB context
    db_context = ""
    if _matches(user_message, _SCHEME_KW):
        schemes = await get_government_schemes(user_message)
        if schemes:
            db_context = "\n\n".join(
                f"Scheme: {s['name']}\n"
                f"Description: {s['description']}\n"
                f"Eligibility: {s['eligibility']}\n"
                f"Documents required: {s['documents']}\n"
                f"Where to apply: {s['apply_at']}\n"
                f"Processing time: {s['timeline']}"
                for s in schemes
            )

    user_prompt = (
        f"Database context (use if relevant):\n{db_context}\n\nUser question: {user_message}"
        if db_context else user_message
    )

    return await _llm(
        system=_sys(_SYSTEM_MAIN, lang),
        user=user_prompt,
        max_tokens=1200,
    )