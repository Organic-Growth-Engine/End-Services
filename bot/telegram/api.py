"""HTTP API so other services (such as the gateway) can broadcast posts.

Run with: uv run uvicorn api:app --port 8002
The chat bot in main.py keeps working independently.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator
from telegram import Bot, Message

from config import BOT_TOKEN, CHAT_IDS
from worker import broadcast_post


class MediaItem(BaseModel):
    type: Literal["photo", "video", "document", "audio", "animation"]
    url: HttpUrl
    caption: str | None = None
    parse_mode: str | None = None


class PublishRequest(BaseModel):
    id: str | int | None = Field(default=None, description="Optional, used in logs.")
    content: str | None = None
    parse_mode: str | None = None
    media: list[MediaItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _needs_content(self) -> "PublishRequest":
        if not (self.content and self.content.strip()) and not self.media:
            raise ValueError("a post needs 'content' or 'media'")
        return self


class ChatResult(BaseModel):
    chat: int | str
    ok: bool
    message_ids: list[int] = Field(default_factory=list)


class PublishResult(BaseModel):
    published: int
    total: int
    results: list[ChatResult]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not BOT_TOKEN or not CHAT_IDS:
        raise RuntimeError("BOT_TOKEN and CHAT_IDS must be set (see .env.example).")
    async with Bot(BOT_TOKEN) as bot:
        app.state.bot = bot
        yield


app = FastAPI(title="Telegram publishing service", version="0.1.0", lifespan=lifespan)


def _message_ids(result: Any) -> list[int]:
    # send_media_group returns a tuple of messages; the other send_* methods one.
    messages = result if isinstance(result, (list, tuple)) else [result]
    return [m.message_id for m in messages if isinstance(m, Message)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/publish", response_model=PublishResult)
async def publish(post: PublishRequest) -> PublishResult:
    """Broadcast a post to every chat in CHAT_IDS.

    Returns 200 when at least one chat received it (check ``results`` for
    failures) and 502 when every chat failed; worker.py logs each failure.
    """
    payload = post.model_dump(mode="json", exclude_none=True)
    raw = await broadcast_post(payload, CHAT_IDS, bot=app.state.bot)
    results = [
        ChatResult(chat=chat, ok=result is not None, message_ids=_message_ids(result))
        for chat, result in raw.items()
    ]
    published = sum(r.ok for r in results)
    outcome = PublishResult(published=published, total=len(results), results=results)
    if published == 0:
        raise HTTPException(502, outcome.model_dump())
    return outcome
