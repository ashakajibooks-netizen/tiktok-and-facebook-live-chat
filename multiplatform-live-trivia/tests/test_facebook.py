"""Standalone Facebook LIVE connectivity & polling test."""
import asyncio
import json
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()

def main() -> None:
    access_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
    if not access_token:
        raise SystemExit("FACEBOOK_ACCESS_TOKEN missing in .env file.")

    config_path = Path(__file__).resolve().parents[1] / "config.json"
    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    fb_cfg = config.get("facebook", {})
    live_video_id = fb_cfg.get("live_video_id")
    
    if not live_video_id:
        raise SystemExit("Set facebook.live_video_id in config.json before running this test.")

    async def poll_once():
        url = f"https://graph.facebook.com/v18.0/{live_video_id}/comments"
        params = {"access_token": access_token, "fields": "id,from,message,created_time"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            print(f"Status: {resp.status_code}")
            print(f"Data: {json.dumps(resp.json(), indent=2)}")

    asyncio.run(poll_once())

if __name__ == "__main__":
    main()