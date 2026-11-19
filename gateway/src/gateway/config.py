"""Gateway settings, read from the environment (see .env.example)."""

import os


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
}

YOUTUBE_TIMEOUT = _number("YOUTUBE_TIMEOUT", "7200")
DEFAULT_TIMEOUT = _number("DEFAULT_TIMEOUT", "300")
MAX_JOBS = int(_number("MAX_JOBS", "1000"))

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))
