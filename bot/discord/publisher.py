"""Build a Discord message from a post and send it to each channel.

Media is sent by URL, never downloaded: images and GIFs become embeds, and
other files (video, audio, documents) are linked in the text, where Discord
shows its own preview for direct links. This avoids Discord's upload size limit.
"""

import asyncio
import logging
from typing import Any

import httpx

from schemas import (
    CONTENT_LIMIT,
    ChannelResult,
    MediaType,
    PublishRequest,
    PublishResult,
)

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_WAIT = 10.0
MAX_ATTEMPTS = 3


def build_message(post: PublishRequest) -> dict[str, Any]:
    links = [
        str(m.url) for m in post.media if m.type not in (MediaType.IMAGE, MediaType.GIF)
    ]
    content = "\n".join(part for part in [post.content, *links] if part)
    if len(content) > CONTENT_LIMIT:
        raise ValueError(
            f"Message is {len(content)} characters including media links; Discord "
            f"allows {CONTENT_LIMIT}."
        )

    embeds = [
        {"image": {"url": str(m.url)}, **({"title": m.alt_text[:256]} if m.alt_text else {})}
        for m in post.media
        if m.type in (MediaType.IMAGE, MediaType.GIF)
    ]
    message: dict[str, Any] = {
        # Never ping @everyone, roles or users from post text.
        "allowed_mentions": {"parse": []},
    }
    if content:
        message["content"] = content
    if embeds:
        message["embeds"] = embeds
    return message


async def send(client: httpx.AsyncClient, channel_id: str, message: dict) -> ChannelResult:
    """Send to one channel. Retries only on 429, which Discord didn't process."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.post(f"/channels/{channel_id}/messages", json=message)
        except httpx.HTTPError as exc:
            # The request may have reached Discord; don't retry and risk a duplicate.
            logger.error("Discord request to %s failed: %s", channel_id, type(exc).__name__)
            return ChannelResult(
                channel_id=channel_id, ok=False,
                error=f"Request failed ({type(exc).__name__}); check the channel before retrying.",
            )

        if response.is_success:
            return ChannelResult(channel_id=channel_id, ok=True, message_id=response.json()["id"])

        if response.status_code == 429 and attempt < MAX_ATTEMPTS:
            wait = float(_json(response).get("retry_after", 1.0))
            if wait <= MAX_RATE_LIMIT_WAIT:
                logger.warning("Rate limited on %s; retrying in %.2fs", channel_id, wait)
                await asyncio.sleep(wait)
                continue

        error = _json(response).get("message") or response.reason_phrase
        logger.error("Discord rejected post to %s: %s %s", channel_id, response.status_code, error)
        return ChannelResult(
            channel_id=channel_id, ok=False, error=f"Discord HTTP {response.status_code}: {error}"
        )
    raise AssertionError("unreachable")


async def broadcast(
    client: httpx.AsyncClient, post: PublishRequest, channel_ids: list[str]
) -> PublishResult:
    message = build_message(post)
    results = await asyncio.gather(*(send(client, cid, message) for cid in channel_ids))
    published = sum(r.ok for r in results)
    return PublishResult(published=published, total=len(results), results=list(results))


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
