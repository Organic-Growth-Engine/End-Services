"""Publish a post supplied by the content service to a Telegram chat."""

import logging

from config import BOT_TOKEN
from publisher import TelegramPublisher
from telegram_client import TelegramClient, TelegramError

logger = logging.getLogger(__name__)


def _validate_request(post: dict, chat: int | str) -> None:
    if not isinstance(post, dict):
        raise TypeError("Post must be an object.")
    if not isinstance(chat, (int, str)) or (isinstance(chat, str) and not chat.strip()):
        raise ValueError("Chat must be a non-empty integer id or @username.")
    if not post.get("content") and not post.get("media"):
        raise RuntimeError("Post has no content or media.")


async def publish_post(
    post: dict,
    chat: int | str,
) -> dict | None:
    """Publish a post to the chat supplied by the caller."""
    post_id = post.get("id") if isinstance(post, dict) else None
    label = post_id or "unknown"

    try:
        if isinstance(chat, str):
            chat = chat.strip()
        _validate_request(post, chat)
        async with TelegramClient(BOT_TOKEN) as client:
            publisher = TelegramPublisher(client)
            result = await publisher.publish(
                chat,
                post.get("content"),
                post.get("media") or [],
                parse_mode=post.get("parse_mode"),
            )
    except (TelegramError, RuntimeError, ValueError, TypeError) as exc:
        logger.error("Could not publish post %s to %s: %s", label, chat, exc)
        return None
    except Exception:
        logger.exception("Unexpected error while publishing post %s to %s", label, chat)
        return None

    logger.info("Published post %s to %s.", label, chat)
    return result
