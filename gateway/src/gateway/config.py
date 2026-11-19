"""Gateway settings, read from the environment (see the repo's .env.example)."""

import json
import os
from typing import Any

from dotenv import load_dotenv

# Finds the nearest .env walking up from this file, i.e. the repo-wide one.
load_dotenv()


def _url(name: str, default: str) -> str | None:
    value = os.getenv(name, default).strip().rstrip("/")
    return value or None


def _number(name: str, default: str) -> float:
    value = float(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value


# None means the platform is disabled.
SERVICE_URLS: dict[str, str | None] = {
    "youtube": _url("YOUTUBE_URL", "http://127.0.0.1:8001"),
    "x": _url("X_URL", "http://127.0.0.1:8000"),
    "telegram": _url("TELEGRAM_URL", "http://127.0.0.1:8002"),
    "facebook": _url("FACEBOOK_URL", "http://127.0.0.1:8003"),
    "instagram": _url("INSTAGRAM_URL", "http://127.0.0.1:8004"),
    "discord": _url("DISCORD_URL", "http://127.0.0.1:8005"),
}

YOUTUBE_TIMEOUT = _number("YOUTUBE_TIMEOUT", "7200")
DEFAULT_TIMEOUT = _number("DEFAULT_TIMEOUT", "300")
MAX_JOBS = int(_number("MAX_JOBS", "1000"))



def _youtube_credentials() -> dict[str, Any] | None:
    """Default channel credentials, used when a request doesn't send its own."""
    raw = os.getenv("YOUTUBE_CREDENTIALS_JSON", "").strip()
    if raw:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("YOUTUBE_CREDENTIALS_JSON must be a JSON object.")
        return value
    fields = {
        "client_id": os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip(),
    }
    if not any(fields.values()):
        return None
    missing = [f"YOUTUBE_{k.upper()}" for k, v in fields.items() if not v]
    if missing:
        raise ValueError(f"Set all YouTube credentials; missing {', '.join(missing)}.")
    return fields


YOUTUBE_CREDENTIALS = _youtube_credentials()

HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
PORT = int(os.getenv("GATEWAY_PORT", "8080"))
