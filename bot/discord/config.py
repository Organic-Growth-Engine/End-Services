"""Settings from the environment / .env (see .env.example)."""

import json
import os

from dotenv import load_dotenv

load_dotenv()


def _parse_channel_ids(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            'DISCORD_CHANNEL_IDS must be a JSON array, e.g. ["123456789012345678"].'
        ) from exc
    if not isinstance(values, list):
        raise ValueError('DISCORD_CHANNEL_IDS must be a JSON array, e.g. ["123456789012345678"].')

    channel_ids: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value.isdecimal():
            raise ValueError(f"Channel id {value!r} must be a numeric Discord id.")
        if value not in channel_ids:
            channel_ids.append(value)
    return channel_ids


BOT_TOKEN = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()

# Every listed channel receives each post. Must be a JSON array.
CHANNEL_IDS = _parse_channel_ids(
    os.getenv("DISCORD_CHANNEL_IDS") or os.getenv("CHANNEL_IDS") or ""
)

API_BASE_URL = (os.getenv("DISCORD_API_BASE_URL") or "https://discord.com/api/v10").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("DISCORD_REQUEST_TIMEOUT") or "30")


def validate() -> None:
    missing = [
        name
        for name, value in (("DISCORD_BOT_TOKEN", BOT_TOKEN), ("DISCORD_CHANNEL_IDS", CHANNEL_IDS))
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
