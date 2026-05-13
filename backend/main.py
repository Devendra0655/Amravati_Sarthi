import json
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.database import get_pool, close_pool
from backend.ai_engine import process_chat_message
import os

BASE_DIR     = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
INDEX_FILE   = FRONTEND_DIR / "scripts" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="Amravati Sarthi API", lifespan=lifespan)

origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR), html=False), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(INDEX_FILE)


@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload      = json.loads(raw)
                user_message = payload.get("text", "").strip()
                user_lat     = float(payload.get("lat", 0.0))
                user_lng     = float(payload.get("lng", 0.0))
                lang         = payload.get("lang", "en").strip().lower()
            except (json.JSONDecodeError, ValueError):
                user_message = raw.strip()
                user_lat, user_lng = 0.0, 0.0
                lang = "en"

            if not user_message:
                continue

            response = await process_chat_message(
                user_message=user_message,
                user_lat=user_lat,
                user_lng=user_lng,
                lang=lang,
            )
            await websocket.send_text(response)
    except WebSocketDisconnect:
        pass