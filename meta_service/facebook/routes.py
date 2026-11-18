from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends

import config
from facebook_client import FacebookClient
from publisher import FacebookPublisher
from schemas import DeleteResult, PageProfile, PublishRequest, PublishResult

router = APIRouter()


async def get_client() -> AsyncIterator[FacebookClient]:
    async with FacebookClient(
        config.ACCESS_TOKEN,
        config.PAGE_ID,
        api_version=config.API_VERSION,
        api_base_url=config.API_BASE_URL,
    ) as client:
        yield client


Client = Annotated[FacebookClient, Depends(get_client)]


async def get_publisher(client: Client) -> FacebookPublisher:
    return FacebookPublisher(client)


Publisher = Annotated[FacebookPublisher, Depends(get_publisher)]


@router.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/page", response_model=PageProfile, tags=["page"])
async def get_page(client: Client) -> PageProfile:
    return PageProfile(**await client.get_page())


@router.post("/publish", response_model=PublishResult, tags=["publishing"])
async def publish(post: PublishRequest, publisher: Publisher) -> PublishResult:
    return await publisher.publish(post.model_dump(mode="json", exclude_none=True))


@router.delete("/post/{post_id}", response_model=DeleteResult, tags=["publishing"])
async def delete_post(post_id: str, client: Client) -> DeleteResult:
    body = await client.delete_post(post_id)
    return DeleteResult(post_id=post_id, success=body.get("success", True))
