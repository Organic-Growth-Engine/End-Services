import json
import os

from dotenv import load_dotenv

load_dotenv()


def _parse_chat_ids(raw: str) -> list[int | str]:
    """Parse a JSON array of chat ids/usernames."""
    raw = (raw or "").strip()
    if not raw:
        return []

    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            'CHAT_IDS must be a JSON array, e.g. ["-1001234567890", "@my_channel"].'
        ) from exc

    if not isinstance(values, list):
        raise TypeError(
            'CHAT_IDS must be a JSON array, e.g. ["-1001234567890", "@my_channel"].'
        )

    chat_ids: list[int | str] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise TypeError(
                "Each entry in CHAT_IDS must be an integer id or @username."
            )
        value = str(value).strip()
        if not value:
            continue
        try:
            chat_ids.append(int(value))
        except ValueError:
            chat_ids.append(value)
    return chat_ids


def _parse_user_id(raw: str) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("OWNER_USER_ID must be an integer Telegram user id.") from exc


BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()

# Optional. When set, only this Telegram user can issue broadcast commands.
OWNER_USER_ID = _parse_user_id(os.getenv("OWNER_USER_ID") or "")

# Every configured chat receives each broadcast. Must be a JSON array.
CHAT_IDS = _parse_chat_ids(os.getenv("CHAT_IDS") or "")
