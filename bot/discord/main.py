"""Discord publishing service.

Run with: uv run uvicorn main:app --port 8005
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException

import config
from publisher import broadcast
from schemas import PublishRequest, PublishResult

USER_AGENT = "DiscordBot (https://github.com/Organic-Growth-Engine/End-Services, 0.1.0)"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config.validate()
    async with httpx.AsyncClient(
        base_url=config.API_BASE_URL,
        headers={"Authorization": f"Bot {config.BOT_TOKEN}", "User-Agent": USER_AGENT},
        timeout=config.REQUEST_TIMEOUT,
    ) as client:
        app.state.client = client
        yield


app = FastAPI(
    title="Discord Publishing Service",
    version="0.1.0",
    description="Publishes posts to the configured Discord channels.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/publish", response_model=PublishResult)
async def publish(post: PublishRequest) -> PublishResult:
    """Post to every channel in CHANNEL_IDS.

    200 when at least one channel received it (check ``results``), 502 when
    every channel failed, 422 for an invalid post.
    """
    try:
        result = await broadcast(app.state.client, post, config.CHANNEL_IDS)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if result.published == 0:
        raise HTTPException(502, result.model_dump())
    return result
