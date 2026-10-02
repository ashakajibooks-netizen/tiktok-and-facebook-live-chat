"""Facebook LIVE Integration Adapter using HTTP Polling."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Optional, Set

import httpx

from app.models import ChatMessage, Platform, PlatformStatus, PlatformStatusType

logger = logging.getLogger(__name__)


class FacebookAdapter:
    def __init__(
        self,
        access_token: str,
        live_video_id: str,
        chat_queue: asyncio.Queue,
        poll_interval_ms: int = 500,
        status_callback=None,
    ) -> None:
        self.access_token = access_token
        self.live_video_id = live_video_id
        self.chat_queue = chat_queue
        self.poll_interval = poll_interval_ms / 1000.0
        self.status_callback = status_callback

        self.status = PlatformStatus(platform=Platform.FACEBOOK.value, state=PlatformStatusType.DISABLED)
        self.seen_message_ids: Set[str] = set()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.dropped_messages = 0

    def _update_status(self, state: PlatformStatusType, detail: str = "") -> None:
        self.status.state = state
        self.status.detail = detail
        if self.status_callback:
            self.status_callback(self.status)

    async def start(self) -> None:
        if self._running:
            return

        if not self.access_token or not self.live_video_id:
            self._update_status(PlatformStatusType.DISABLED, "Missing token or live_video_id")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        self._update_status(PlatformStatusType.CONNECTING, "Polling Facebook LIVE...")
        url = f"https://graph.facebook.com/v18.0/{self.live_video_id}/comments"
        params = {
            "access_token": self.access_token,
            "fields": "id,from,message,created_time",
            "order": "reverse_chronological",
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            self._update_status(PlatformStatusType.CONNECTED, f"Polling Video ID: {self.live_video_id}")
            while self._running:
                try:
                    received_at = time.monotonic()
                    resp = await client.get(url, params=params)
                    
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        for item in reversed(data):  # Process oldest to newest
                            msg_id = item.get("id")
                            if not msg_id or msg_id in self.seen_message_ids:
                                continue

                            self.seen_message_ids.add(msg_id)
                            user_data = item.get("from", {})
                            user_id = str(user_data.get("id", "unknown"))
                            username = user_data.get("name", user_id)
                            text = item.get("message", "")

                            created_str = item.get("created_time")
                            created_dt = None
                            if created_str:
                                try:
                                    created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                                except ValueError:
                                    pass

                            msg = ChatMessage(
                                platform=Platform.FACEBOOK.value,
                                user_id=user_id,
                                username=username,
                                text=text,
                                received_at=received_at,
                                message_id=msg_id,
                                platform_created_at=created_dt,
                            )

                            try:
                                self.chat_queue.put_nowait(msg)
                            except asyncio.QueueFull:
                                self.dropped_messages += 1
                                logger.warning(f"Chat Queue full. Dropped Facebook comment ID {msg_id}")

                except Exception as exc:
                    logger.error(f"Error polling Facebook comments: {exc}")
                    self.status.reconnect_attempts += 1

                await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._update_status(PlatformStatusType.DISABLED, "Stopped")