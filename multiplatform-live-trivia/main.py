"""FastAPI Application Entry Point & Unified Runner."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
from typing import Set

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.trivia import GameState, TriviaEngine
from app.integrations.facebook import FacebookAdapter
from app.integrations.tiktok import TikTokAdapter
from app.models import GameCommand, GameCommandType, GameSnapshot
from app.services.persistence import atomic_write_file, save_json_atomic
from app.services.question_loader import load_questions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config.json"

# Load config
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

load_dotenv(BASE_DIR / ".env")
active_websockets: Set[WebSocket] = set()


async def broadcast_snapshot(snapshot: GameSnapshot) -> None:
    if not active_websockets:
        return
    payload = json.dumps(asdict(snapshot))
    to_remove = set()
    for ws in active_websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            to_remove.add(ws)
    active_websockets.difference_update(to_remove)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Queues
    chat_maxsize = config.get("queues", {}).get("chat_maxsize", 10000)
    command_maxsize = config.get("queues", {}).get("command_maxsize", 100)
    chat_queue = asyncio.Queue(maxsize=chat_maxsize)
    command_queue = asyncio.Queue(maxsize=command_maxsize)

    # 2. Questions
    q_file = BASE_DIR / "data" / config.get("questions_file", "questions.json")
    if not q_file.exists():
        q_file = BASE_DIR / "questions.json"
    questions = load_questions(q_file)

    # 3. Game Engine
    engine = TriviaEngine(
        questions=questions,
        chat_queue=chat_queue,
        command_queue=command_queue,
        question_time_sec=config.get("game", {}).get("question_time_seconds", 10.0),
        transition_time_sec=config.get("game", {}).get("transition_time_seconds", 3.0),
        fuzzy_threshold=config.get("game", {}).get("fuzzy_threshold", 85.0),
        drain_idle_ms=config.get("timing", {}).get("drain_idle_ms", 50.0),
        drain_hard_cap_ms=config.get("timing", {}).get("drain_hard_cap_ms", 1500.0),
    )

    app.state.engine = engine
    app.state.command_queue = command_queue
    app.state.chat_queue = chat_queue

    # 4. Adapters
    tiktok_cfg = config.get("tiktok", {})
    tiktok_adapter = None
    if tiktok_cfg.get("enabled", True):
        tiktok_adapter = TikTokAdapter(username=tiktok_cfg.get("username", ""), chat_queue=chat_queue)
        asyncio.create_task(tiktok_adapter.start())

    fb_cfg = config.get("facebook", {})
    fb_token = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    fb_adapter = None
    if fb_cfg.get("enabled", True) and fb_token:
        fb_adapter = FacebookAdapter(
            access_token=fb_token,
            live_video_id=fb_cfg.get("live_video_id", ""),
            chat_queue=chat_queue,
            poll_interval_ms=fb_cfg.get("poll_interval_ms", 500),
        )
        asyncio.create_task(fb_adapter.start())

    # 5. Engine Task & WebSocket Periodic Dispatch
    engine.start()

    async def broadcast_loop():
        while engine.state != GameState.STOPPED:
            snap = engine.get_snapshot()
            # Update adapter statuses in snapshot
            if tiktok_adapter:
                snap.platforms["tiktok"] = getattr(tiktok_adapter, "status", "CONNECTED")
            if fb_adapter:
                snap.platforms["facebook"] = fb_adapter.status.state.value if hasattr(fb_adapter.status.state, "value") else str(fb_adapter.status.state)
            await broadcast_snapshot(snap)
            
            # Persist leaderboard
            if snap.state in (GameState.RESULT.value, GameState.FINISHED.value):
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                save_json_atomic(DATA_DIR / "leaderboard.json", snap.leaderboard)
                txt_lines = [f"#{i+1} {p['display_name']}: {p['score']} pts" for i, p in enumerate(snap.leaderboard[:5])]
                atomic_write_file(DATA_DIR / "leaderboard.txt", "\n".join(txt_lines))

            await asyncio.sleep(0.1)

    broadcast_task = asyncio.create_task(broadcast_loop())

    yield

    # Teardown
    broadcast_task.cancel()
    if tiktok_adapter:
        await tiktok_adapter.stop()
    if fb_adapter:
        await fb_adapter.stop()
    await engine.stop()


app = FastAPI(title="Multiplatform LIVE Trivia", lifespan=lifespan)

# Mount web directory
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def get_index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/overlay")
async def get_overlay():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/status")
async def get_status():
    if hasattr(app.state, "engine"):
        return JSONResponse(asdict(app.state.engine.get_snapshot()))
    return JSONResponse({"status": "starting"})


@app.post("/game/start")
async def start_game():
    engine: TriviaEngine = getattr(app.state, "engine", None)
    if not engine or engine.state not in (GameState.WAITING_FOR_START, GameState.IDLE):
        raise HTTPException(status_code=400, detail="Cannot start: game not in WAITING_FOR_START state")
    await app.state.command_queue.put(GameCommand(command=GameCommandType.START))
    return {"status": "ok", "message": "START command queued"}


@app.post("/game/stop")
async def stop_game():
    if hasattr(app.state, "command_queue"):
        await app.state.command_queue.put(GameCommand(command=GameCommandType.STOP))
        return {"status": "ok", "message": "STOP command queued"}
    raise HTTPException(status_code=500, detail="Command queue uninitialized")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_websockets.add(ws)
    if hasattr(app.state, "engine"):
        await ws.send_text(json.dumps(asdict(app.state.engine.get_snapshot())))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        active_websockets.discard(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)