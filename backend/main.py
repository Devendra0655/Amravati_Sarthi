"""
Amravati Sarthi — backend/main.py  (fixed)
Fixes:
  1. DB pool failure is non-fatal — app starts even if DB is unreachable
  2. WebSocket keepalive ping every 30s — prevents Render from dropping idle connections
  3. Graceful error handling so WS never silently dies
"""

import json
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# ── Safe DB import ────────────────────────────────────────
# If DB is unreachable, we log the error but DON'T crash the server
_db_available = False
try:
    from backend.database import get_pool, close_pool
    _db_available = True
except Exception as e:
    print(f"⚠️  DB module import failed (will run without DB): {e}")

# ── AI engine import ──────────────────────────────────────
from backend.ai_engine import process_chat_message


# ── Lifespan: DB connect is best-effort ──────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    if _db_available:
        try:
            await asyncio.wait_for(get_pool(), timeout=8.0)
            print("✅  Database pool connected")
        except asyncio.TimeoutError:
            print("⚠️  DB connection timed out — running without database")
        except Exception as e:
            print(f"⚠️  DB connection failed — running without database: {e}")
    else:
        print("⚠️  Running without database (module not available)")

    yield   # ← server runs here

    if _db_available:
        try:
            await close_pool()
        except Exception:
            pass


# ── App ───────────────────────────────────────────────────
app = FastAPI(title="Amravati Sarthi API", lifespan=lifespan)

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "https://amravati-sarthi.vercel.app,http://localhost:5500,http://127.0.0.1:5500"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health (Render pings this to keep service alive) ─────
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "Amravati Sarthi API is running 🏛️"}


# ── WebSocket chat ────────────────────────────────────────
@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔌  WebSocket client connected")

    # Keepalive: ping every 30s so Render doesn't kill idle WebSocket
    # (Render free tier drops idle connections after ~60s)
    async def _keepalive():
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send_text("__ping__")
            except Exception:
                break

    keepalive_task = asyncio.create_task(_keepalive())

    try:
        while True:
            raw = await websocket.receive_text()

            # Ignore pong from client
            if raw.strip() == "__pong__":
                continue

            # Parse payload
            try:
                payload      = json.loads(raw)
                user_message = payload.get("text", "").strip()
                user_lat     = float(payload.get("lat", 20.9320))
                user_lng     = float(payload.get("lng", 77.7523))
                lang         = payload.get("lang", "en").strip().lower()
            except (json.JSONDecodeError, ValueError):
                user_message = raw.strip()
                user_lat, user_lng = 20.9320, 77.7523
                lang = "en"

            if not user_message:
                continue

            # Process with timeout so a slow AI call never hangs forever
            try:
                response = await asyncio.wait_for(
                    process_chat_message(
                        user_message=user_message,
                        user_lat=user_lat,
                        user_lng=user_lng,
                        lang=lang,
                    ),
                    timeout=25.0
                )
                await websocket.send_text(response)

            except asyncio.TimeoutError:
                await websocket.send_text(
                    "Sorry, the request took too long. Please try again."
                    if lang == "en" else
                    "माफ करा, विनंती खूप वेळ घेतली. पुन्हा प्रयत्न करा."
                )
            except Exception as e:
                print(f"❌  process_chat_message error: {e}")
                await websocket.send_text(
                    "Something went wrong. Please try again."
                    if lang == "en" else
                    "काहीतरी चुकले. पुन्हा प्रयत्न करा."
                )

    except WebSocketDisconnect:
        print("🔌  WebSocket client disconnected")
    except Exception as e:
        print(f"❌  WebSocket error: {e}")
    finally:
        keepalive_task.cancel()