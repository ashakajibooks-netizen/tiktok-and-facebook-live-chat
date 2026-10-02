"""TikTok Live Integration Module."""
from __future__ import annotations

import asyncio
import logging

from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent

# Handle version differences across TikTokLive exception module locations
try:
    from TikTokLive.client.errors import UserOfflineError
except ImportError:
    try:
        from TikTokLive.errors import UserOfflineError
    except ImportError:
        UserOfflineError = Exception

from app.models import ChatMessage, Platform

logger = logging.getLogger(__name__)


class TikTokAdapter:

    def __init__(self, username: str, chat_queue: asyncio.Queue[ChatMessage]):
        clean_username = username.lstrip("@").strip()
        self.username = clean_username
        self.chat_queue = chat_queue
        self.client = TikTokLiveClient(unique_id=self.username)
        self._is_running = False

        @self.client.on(CommentEvent)
        async def on_comment(event: CommentEvent) -> None:
            msg = ChatMessage(
                platform=Platform.TIKTOK,
                user_id=str(event.user.user_id),
                display_name=event.user.nickname or event.user.unique_id,
                message=event.comment,
                timestamp=float(event.timestamp / 1000.0) if event.timestamp else 0.0,
            )
            try:
                self.chat_queue.put_nowait(msg)
            except asyncio.QueueFull:
                logger.warning("Chat queue full, dropping TikTok message from %s", msg.display_name)

    async def start(self) -> None:
        if not self.username:
            logger.info("TikTok username not configured, skipping TikTok integration.")
            return

        self._is_running = True
        logger.info("Starting TikTok client loop for @%s...", self.username)

        while self._is_running:
            try:
                logger.info("Connecting to TikTok Live stream for @%s...", self.username)
                await self.client.start()
            except Exception as e:
                if isinstance(e, UserOfflineError) or e.__class__.__name__ == "UserOfflineError":
                    logger.warning(
                        "TikTok user @%s is currently offline. Retrying in 30 seconds...",
                        self.username,
                    )
                    await asyncio.sleep(30)
                elif isinstance(e, asyncio.CancelledError):
                    self._is_running = False
                    break
                else:
                    logger.error("TikTok error for @%s: %s. Retrying in 15 seconds...", self.username, e)
                    await asyncio.sleep(15)

    async def stop(self) -> None:
        self._is_running = False
        try:
            if self.client.is_connected:
                await self.client.disconnect()
        except Exception as e:
            logger.debug("Error disconnecting TikTok client: %s", e)