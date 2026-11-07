"""Publish a post supplied by the content service to one or more Telegram chats."""

import asyncio
import logging

from telegram import Bot
from telegram.error import TelegramError

from config import BOT_TOKEN
from publisher import TelegramPublisher

logger = logging.getLogger(__name__)

Chat = int | str


def _normalize_chat(chat: Chat) -> Chat:
    if isinstance(chat, str):
        chat = chat.strip()
    if not isinstance(chat, (int, str)) or (isinstance(chat, str) and not chat):
        raise ValueError("Chat must be a non-empty integer id or @username.")
    return chat


def _validate_request(post: dict, chat: Chat) -> None:
    if not isinstance(post, dict):
        raise TypeError("Post must be an object.")
    _normalize_chat(chat)
    if not post.get("content") and not post.get("media"):
        raise RuntimeError("Post has no content or media.")


async def _publish(bot: Bot, post: dict, chat: Chat) -> object:
    publisher = TelegramPublisher(bot)
    return await publisher.publish(
        chat,
        post.get("content"),
        post.get("media") or [],
        parse_mode=post.get("parse_mode"),
    )


async def publish_post(
    post: dict,
    chat: Chat,
    *,
    bot: Bot | None = None,
) -> object | None:
    """Publish a post to a single chat."""
    post_id = post.get("id") if isinstance(post, dict) else None
    label = post_id or "unknown"

    try:
        chat = _normalize_chat(chat)
        _validate_request(post, chat)
        if bot is None:
            async with Bot(BOT_TOKEN) as owned_bot:
                result = await _publish(owned_bot, post, chat)
        else:
            result = await _publish(bot, post, chat)
    except (TelegramError, RuntimeError, ValueError, TypeError) as exc:
        logger.error("Could not publish post %s to %s: %s", label, chat, exc)
        return None
    except Exception:
        logger.exception("Unexpected error while publishing post %s to %s", label, chat)
        return None

    logger.info("Published post %s to %s.", label, chat)
    return result


async def broadcast_post(
    post: dict,
    chats: list[Chat],
    *,
    bot: Bot | None = None,
) -> dict[Chat, object | None]:
    """Publish a post to every configured chat.

    Returns a mapping of chat -> Telegram response (or 'None' on failure).
    """
    if not isinstance(chats, (list, tuple)) or not chats:
        raise ValueError("At least one chat id is required to broadcast a post.")

    normalized = []
    for chat in chats:
        chat = _normalize_chat(chat)
        if chat not in normalized:
            normalized.append(chat)

    if bot is None:
        async with Bot(BOT_TOKEN) as owned_bot:
            return await _broadcast(owned_bot, post, normalized)
    return await _broadcast(bot, post, normalized)


async def _broadcast(
    bot: Bot,
    post: dict,
    chats: list[Chat],
) -> dict[Chat, object | None]:
    results = await asyncio.gather(
        *(publish_post(post, chat, bot=bot) for chat in chats)
    )
    return dict(zip(chats, results))
