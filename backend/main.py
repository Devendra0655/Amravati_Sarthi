import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.database import get_pool, close_pool
from backend.ai_engine import process_chat_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="Amravati Sarthi API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "Amravati Sarthi API is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


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