"""Standalone TikTok LIVE connectivity test.

This script intentionally does NOT touch the trivia engine or scoring.
Its only job is to verify that TikTokLive can connect and deliver live events.

Run from the project root:
    python tests/test_tiktok.py

Set the TikTok broadcaster username in config.json under:
    tiktok.username
"""

from __future__ import annotations

import json
from pathlib import Path


def load_username() -> str:
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    username = str(config.get("tiktok", {}).get("username", "")).strip()
    if not username or username == "@yourusername":
        raise SystemExit(
            "Set tiktok.username in config.json to the LIVE broadcaster username "
            "before running this test."
        )

    return username if username.startswith("@") else f"@{username}"


def main() -> None:
    try:
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent
    except ImportError as exc:
        raise SystemExit(
            "TikTokLive is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc

    username = load_username()
    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent) -> None:
        print(f"TikTok: CONNECTED to @{event.unique_id}")
        print(f"Room ID: {client.room_id}")
        print("Waiting for comments... Press Ctrl+C to stop.")

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent) -> None:
        user_id = getattr(event.user, "user_id", None) or getattr(
            event.user, "unique_id", "unknown"
        )
        display_name = getattr(event.user, "nickname", "unknown")
        print(f"COMMENT | user_id={user_id} | name={display_name} | text={event.comment}")

    @client.on(DisconnectEvent)
    async def on_disconnect(_: DisconnectEvent) -> None:
        print("TikTok: DISCONNECTED")

    # Required by the project specification for the standalone test.
    client.run()


if __name__ == "__main__":
    main()
