"""FastAPI Web Server & WebSocket Overlay Broadcast."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import logging
from pathlib import Path
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.engine import TriviaEngine
from app.models import GameCommand, GameCommandType, GameSnapshot

logger = logging.getLogger(__name__)


def create_app(engine: TriviaEngine, config: dict) -> FastAPI:
    app = FastAPI(title="Multiplatform Live Trivia Overlay")

    # Serve static assets if the folder exists
    static_dir = Path("static")
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    active_websockets: Set[WebSocket] = set()

    async def broadcast_snapshot(snapshot: GameSnapshot) -> None:
        if not active_websockets:
            return
        data = asdict(snapshot)
        message = json.dumps(data)
        to_remove = set()
        for ws in active_websockets:
            try:
                await ws.send_text(message)
            except Exception:
                to_remove.add(ws)
        active_websockets.difference_update(to_remove)

    def on_snapshot_update(snapshot: GameSnapshot) -> None:
        asyncio.create_task(broadcast_snapshot(snapshot))

    engine.snapshot_callback = on_snapshot_update

    @app.get("/api/status")
    async def get_status() -> JSONResponse:
        return JSONResponse(asdict(engine.get_snapshot()))

    @app.post("/api/control")
    async def post_control(payload: Dict[str, str]) -> JSONResponse:
        action = payload.get("action", "").upper()
        if action == "START":
            engine.handle_command(GameCommand(command=GameCommandType.START))
            return JSONResponse({"status": "ok", "action": "START"})
        elif action == "STOP":
            engine.handle_command(GameCommand(command=GameCommandType.STOP))
            return JSONResponse({"status": "ok", "action": "STOP"})
        return JSONResponse(
            {"status": "error", "message": f"Unknown action '{action}'"}, status_code=400
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        active_websockets.add(websocket)
        await websocket.send_text(json.dumps(asdict(engine.get_snapshot())))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            active_websockets.discard(websocket)

    return app