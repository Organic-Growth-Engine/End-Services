from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends

import config
from instagram_client import InstagramClient
from publisher import InstagramPublisher
from schemas import AccountProfile, PublishingLimit, PublishRequest, PublishResult

router = APIRouter()


async def get_client() -> AsyncIterator[InstagramClient]:
    async with InstagramClient(
        config.ACCESS_TOKEN,
        config.USER_ID,
        api_version=config.API_VERSION,
        api_base_url=config.API_BASE_URL,
    ) as client:
        yield client


Client = Annotated[InstagramClient, Depends(get_client)]


async def get_publisher(client: Client) -> InstagramPublisher:
    return InstagramPublisher(client)


Publisher = Annotated[InstagramPublisher, Depends(get_publisher)]


@router.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/account", response_model=AccountProfile, tags=["account"])
async def get_account(client: Client) -> AccountProfile:
    return AccountProfile(**await client.get_account())


@router.get("/publishing-limit", response_model=PublishingLimit, tags=["account"])
async def get_publishing_limit(client: Client) -> PublishingLimit:
    body = await client.get_publishing_limit()
    data = (body.get("data") or [{}])[0]
    quota = data.get("config") or {}
    return PublishingLimit(
        quota_usage=data.get("quota_usage", 0),
        quota_total=quota.get("quota_total", 0),
        quota_duration=quota.get("quota_duration", 0),
    )


@router.post("/publish", response_model=PublishResult, tags=["publishing"])
async def publish(post: PublishRequest, publisher: Publisher) -> PublishResult:
    return await publisher.publish(post.model_dump(mode="json", exclude_none=True))
