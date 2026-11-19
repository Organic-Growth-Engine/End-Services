"""Connect the bot to Discord's Gateway once, then exit.

Discord requires a bot to have connected to the Gateway at least once before
it can send messages over the REST API. Run this once after creating the bot:

    uv run python connect_once.py
"""

import asyncio
import json
import sys

import httpx
import websockets

import config

GATEWAY_QUERY = "/?v=10&encoding=json"


async def main() -> int:
    if not config.BOT_TOKEN:
        print("Set DISCORD_BOT_TOKEN in .env first.", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bot {config.BOT_TOKEN}"}
    async with httpx.AsyncClient(base_url=config.API_BASE_URL, headers=headers) as client:
        response = await client.get("/gateway/bot")
    if response.status_code == 401:
        print("Discord rejected the token (401). Reset it in the Developer Portal.", file=sys.stderr)
        return 1
    response.raise_for_status()

    async with websockets.connect(response.json()["url"] + GATEWAY_QUERY) as ws:
        json.loads(await ws.recv())  # HELLO
        await ws.send(json.dumps({
            "op": 2,  # IDENTIFY
            "d": {
                "token": config.BOT_TOKEN,
                "intents": 0,
                "properties": {"os": sys.platform, "browser": "end-services", "device": "end-services"},
            },
        }))
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if event.get("t") == "READY":
                user = event["d"]["user"]
                print(f"Connected as {user['username']} ({user['id']}). You can now publish.")
                return 0
            if event.get("op") == 9:  # INVALID_SESSION
                print("Discord refused the session; check the token.", file=sys.stderr)
                return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
