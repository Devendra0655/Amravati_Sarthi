import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)

MOCK_AI = os.getenv("MOCK_AI", "false").strip().lower() in ("true", "1", "yes")
_client = None if MOCK_AI else AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
_MODEL  = "llama-3.3-70b-versatile"

# ── Safe DB imports — fall back to None if DB is broken ──────────────────────
try:
    from backend.database import get_government_schemes as _db_schemes
    from backend.database import get_nearby_businesses  as _db_businesses
    _DB_OK = True
except Exception as e:
    print(f"⚠️  DB functions unavailable: {e}")
    _DB_OK = False

async def _safe_get_businesses(hint, lat, lng):
    """Call DB; return [] silently if DB is down."""
    if not _DB_OK:
        return []
    try:
        return await asyncio.wait_for(_db_businesses(hint, lat, lng), timeout=6.0) or []
    except Exception as e:
        print(f"⚠️  get_nearby_businesses failed: {e}")
        return []

async def _safe_get_schemes(query):
    """Call DB; return [] silently if DB is down."""
    if not _DB_OK:
        return []
    try:
        return await asyncio.wait_for(_db_schemes(query), timeout=6.0) or []
    except Exception as e:
        print(f"⚠️  get_government_schemes failed: {e}")
        return []

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

# ── Emergency data ────────────────────────────────────────────────────────────
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
    "hi": (
        "🚨 आपातकालीन संपर्क — अमरावती\n\n"
        "• पुलिस: 100 | अमरावती नियंत्रण कक्ष: 0721-2662100\n"
        "• एम्बुलेंस: 108 (मुफ्त, 24×7)\n"
        "• दमकल: 101 | अमरावती: 0721-2570101\n"
        "• महिला हेल्पलाइन: 1091\n"
        "• बाल हेल्पलाइन: 1098\n"
        "• आपदा प्रबंधन: 1070\n"
        "• सिविल अस्पताल अमरावती: 0721-2662100\n"
        "• सभी आपातकालीन सेवाएं: 112"
    ),
}

# ── Fallback mock businesses (used when DB is down) ───────────────────────────
_MOCK_HOSPITALS = [
    {"name": "Amravati Civil Hospital",     "category": "hospital", "address": "Rajapeth, Amravati",        "lat": 20.9374, "lng": 77.7596, "phone": "0721-2662100",   "opening_hours": "24/7",        "distance_km": 0.8},
    {"name": "Jawaharlal Nehru Hospital",   "category": "hospital", "address": "Camp Area, Amravati",       "lat": 20.9310, "lng": 77.7540, "phone": "0721-2550100",   "opening_hours": "24/7",        "distance_km": 1.4},
    {"name": "Daga Memorial Hospital",      "category": "hospital", "address": "Jaistambh Chowk, Amravati","lat": 20.9325, "lng": 77.7558, "phone": "0721-2560200",   "opening_hours": "24/7",        "distance_km": 1.8},
]
_MOCK_PHARMACY = [
    {"name": "Shri Medicals & Pharmacy",    "category": "pharmacy", "address": "Badnera Road, Amravati",   "lat": 20.9310, "lng": 77.7540, "phone": "+91-9876543210", "opening_hours": "08:00-22:00", "distance_km": 1.2},
    {"name": "Apollo Pharmacy",             "category": "pharmacy", "address": "Rajapeth, Amravati",       "lat": 20.9370, "lng": 77.7580, "phone": "+91-9823100002", "opening_hours": "08:00-22:00", "distance_km": 1.6},
]
_MOCK_ATM = [
    {"name": "SBI ATM",                     "category": "atm",      "address": "Jaistambh Square, Amravati","lat": 20.9330, "lng": 77.7560, "phone": None,            "opening_hours": "24/7",        "distance_km": 0.6},
    {"name": "HDFC Bank ATM",               "category": "atm",      "address": "Rajapeth, Amravati",       "lat": 20.9360, "lng": 77.7575, "phone": None,            "opening_hours": "24/7",        "distance_km": 1.1},
]
_MOCK_RESTAURANT = [
    {"name": "Hotel Tapovan",               "category": "restaurant","address": "Rajapeth, Amravati",       "lat": 20.9345, "lng": 77.7565, "phone": "+91-9823100003", "opening_hours": "09:00-23:00", "distance_km": 0.9},
    {"name": "Panchavati Restaurant",       "category": "restaurant","address": "Badnera Road, Amravati",   "lat": 20.9300, "lng": 77.7535, "phone": "+91-9823100004", "opening_hours": "10:00-22:30", "distance_km": 1.5},
]
_MOCK_DEFAULT = _MOCK_HOSPITALS  # fallback for unknown categories

def _get_mock_businesses(hint: str) -> list:
    """Return mock data matching the category hint when DB is unavailable."""
    h = hint.lower()
    if any(k in h for k in ["hospital", "doctor", "रुग्णालय", "हॉस्पिटल"]):
        return _MOCK_HOSPITALS
    if any(k in h for k in ["pharmacy", "medicine", "औषध", "फार्मसी"]):
        return _MOCK_PHARMACY
    if any(k in h for k in ["atm", "cash", "पैसे"]):
        return _MOCK_ATM
    if any(k in h for k in ["restaurant", "food", "जेवण", "रेस्टॉरंट"]):
        return _MOCK_RESTAURANT
    return _MOCK_DEFAULT

# ── System prompts ────────────────────────────────────────────────────────────
_LANG_RULE = {
    "en": (
        "MANDATORY LANGUAGE RULE: The user might type in a mix of English, Hindi, or Marathi. "
        "Understand their core intent, but your ENTIRE response MUST be in grammatically correct, "
        "clear English only. Do not use any Marathi or Hindi words."
    ),
    "mr": (
        "अनिवार्य भाषा नियम: वापरकर्ता कदाचित इंग्रजी, हिंदी किंवा मराठी मिश्रित भाषेत टाईप करेल. "
        "त्यांचा उद्देश समजून घ्या, परंतु तुमचे संपूर्ण उत्तर केवळ शुद्ध, व्याकरणदृष्ट्या अचूक मराठीत असावे. "
        "कोणतेही इंग्रजी किंवा हिंदी शब्द वापरू नका."
    ),
    "hi": (
        "अनिवार्य भाषा नियम: उपयोगकर्ता अंग्रेजी, हिंदी या मराठी मिश्रित भाषा में टाइप कर सकता है। "
        "उनके इरादे को समझें, लेकिन आपका पूरा उत्तर केवल शुद्ध, व्याकरणिक रूप से सही हिंदी में होना चाहिए। "
        "किसी भी अंग्रेजी या मराठी शब्दों का उपयोग न करें। आसान और सुलभ भाषा का प्रयोग करें।"
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
1. NO FLUFF: Answer ONLY what is explicitly asked. Zero preamble, zero conversational filler, and no unrequested explanations.
2. STRICT INTENT MATCHING: If the user asks for physical locations (e.g., "hospitals"), you MUST list the actual physical places. If the provided database context only contains phone numbers, ignore the context and use your AI training to list the real places.
3. FORMATTING: ALWAYS structure your responses using clean Markdown. Use bold headings (**Heading**), numbered lists (1., 2.) for rankings, bullet points for details, and short paragraphs.
4. LOCATION BOUNDARY: You only provide places in Amravati. If the user asks for something outside Amravati (like beaches, snow, or foreign cities), politely explain it doesn't exist here and DO NOT generate any map links.
5. DIRECTIONS RULE: ONLY append the clickable Google Maps link [📍 Get Directions](https://www.google.com/maps/search/?api=1&query=PLACE_NAME) when the user EXPLICITLY asks for recommendations, places to visit, or direct locations. Do NOT append links for general informational mentions.
6. For scheme queries: always include eligibility criteria, exact documents required, \
   where and how to apply, processing timeline, and benefit amount.
7. For general queries: answer completely as a knowledgeable expert would.
8. Use exact figures: amounts, dates, percentages — be precise.
9. Proofread your response for grammar and spelling before outputting.
10. If the database context provided is relevant, incorporate it accurately.

{lang_rule}"""

_SYSTEM_LOC = """\
You are "Amravati Sarthi", a smart city assistant for Amravati, Maharashtra.
The user is searching for nearby services. Real local business data is provided below.

INSTRUCTIONS:
1. If the user asks for a specific specialty (e.g., "heart hospital", "best restaurant", "children's doctor"): 
   - Analyze the provided results and recommend the one that best matches their specific need based on its name or category.
   - Briefly explain *why* you are recommending it (e.g., "Since you need a heart specialist, I recommend...").
2. If it is a general request (e.g., "hospitals near me"):
   - Simply recommend the closest one.
3. Keep your response warm, helpful, and brief (2-3 sentences). 
The UI will plot them on the map automatically, so do not list all the results.

{lang_rule}"""

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


# ── Main entry point ──────────────────────────────────────────────────────────
async def process_chat_message(
    user_message: str,
    user_lat: float = 0.0,
    user_lng: float = 0.0,
    lang: str = "en",
) -> str:

    # ── Emergency — instant, no LLM or DB needed ─────────────────────────────
    if _matches(user_message, _EMERGENCY_KW):
        return _EMERGENCY.get(lang, _EMERGENCY["en"])

    # ── Location query ────────────────────────────────────────────────────────
    if _matches(user_message, _LOCATION_KW):
        hint = _category_hint(user_message) or user_message

        # Try DB first; fall back to mock data if DB is down
        if user_lat != 0.0 and user_lng != 0.0:
            businesses = await _safe_get_businesses(hint, user_lat, user_lng)
        else:
            businesses = []

        # If DB returned nothing (down or no results), use mock data
        if not businesses:
            businesses = _get_mock_businesses(hint)

        context = "\n\n".join(
            f"Name: {b['name']}\nCategory: {b['category']}\n"
            f"Address: {b['address']}\nDistance: {b['distance_km']} km\n"
            f"Phone: {b.get('phone') or 'N/A'}\nHours: {b.get('opening_hours') or 'N/A'}"
            for b in businesses
        )

        # Generate summary via LLM
        try:
            summary = await _llm(
                system=_sys(_SYSTEM_LOC, lang),
                user=f"User asked: {user_message}\n\nNearby results ({len(businesses)} found):\n{context}",
                max_tokens=160,
            )
        except Exception as e:
            print(f"⚠️  LLM summary failed: {e}")
            summary = (
                f"मला {len(businesses)} ठिकाणे सापडली. सर्वात जवळचे {businesses[0]['name']} आहे, {businesses[0]['distance_km']} km अंतरावर."
                if lang == "mr" else
                f"I found {len(businesses)} nearby results. The closest is {businesses[0]['name']}, {businesses[0]['distance_km']} km away."
            )

        return f"LOCATIONS:{json.dumps(businesses, ensure_ascii=False)}||{summary}"

    # ── Scheme / general query ────────────────────────────────────────────────
    db_context = ""
    if _matches(user_message, _SCHEME_KW):
        schemes = await _safe_get_schemes(user_message)
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

    if db_context:
        user_prompt = f"""Database context (use this verified data):
    {db_context}

    User question: {user_message}

    CRITICAL INSTRUCTIONS - USE COMMON SENSE:
    1. LOGIC & INTENT: Answer the user intelligently based on reality. If they ask for family weekend spots, suggest actual parks or tourist spots (like Wadali Talao or Bamboo Garden). DO NOT suggest hospitals, colleges, or random buildings for leisure.
    2. AMRAVATI ONLY: Only recommend real places located in Amravati district. If they ask for something that doesn't exist here (like a beach), politely say so.
    3. STRICT MAP LINKS: For EVERY single physical place you list, you MUST append a clickable map link immediately after its name using this exact format:
       [📍 Get Directions](https://www.google.com/maps/search/?api=1&query=INSERT_PLACE_NAME+Amravati)
    4. FORMATTING: Use clean lists. NO fluff. NEVER tell the user to "search online for directions."
    """
    else:
        user_prompt = f"""The requested data is not in the local database. Answer based on your AI training.

    CRITICAL INSTRUCTIONS - USE COMMON SENSE:
    1. LOGIC & INTENT: Answer intelligently based on reality. If the user asks for weekend trips, suggest actual tourist spots. DO NOT suggest hospitals or colleges for leisure.
    2. AMRAVATI ONLY: Only recommend real places in Amravati district. If they ask for something that doesn't exist here (like a beach), politely explain that Amravati is landlocked.
    3. STRICT MAP LINKS: For EVERY single physical place you list, you MUST append a clickable map link immediately after its name using this exact format:
       [📍 Get Directions](https://www.google.com/maps/search/?api=1&query=INSERT_PLACE_NAME+Amravati)
    4. FORMATTING: Use clean numbered lists. NO fluff. NEVER tell the user to "search online for directions."

    User question: {user_message}"""

    try:
        return await _llm(
            system=_sys(_SYSTEM_MAIN, lang),
            user=user_prompt,
            max_tokens=1200,
        )
    except Exception as e:
        print(f"❌  LLM call failed: {e}")
        return (
            "माफ करा, सध्या उत्तर देता येत नाही. कृपया पुन्हा प्रयत्न करा."
            if lang == "mr" else
            "Sorry, I couldn't process your request right now. Please try again."
        )