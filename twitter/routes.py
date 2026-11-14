from typing import Annotated

from fastapi import APIRouter, Depends

import config
from publisher import XPublisher
from schemas import AccountProfile, DeleteResult, PostId, PublishRequest, PublishResult
from x_client import XClient


def get_client() -> XClient:
    return XClient(
        config.API_KEY,
        config.API_SECRET,
        config.ACCESS_TOKEN,
        config.ACCESS_TOKEN_SECRET,
        base_url=config.API_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
    )


Client = Annotated[XClient, Depends(get_client)]


def get_publisher(client: Client) -> XPublisher:
    return XPublisher(client)


Publisher = Annotated[XPublisher, Depends(get_publisher)]

router = APIRouter()


@router.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/account", response_model=AccountProfile, tags=["account"])
async def get_account(client: Client) -> AccountProfile:
    return AccountProfile(**await client.get_me())


@router.post("/publish", response_model=PublishResult, tags=["publishing"])
async def publish(post: PublishRequest, publisher: Publisher) -> PublishResult:
    return await publisher.publish(post)


@router.delete("/posts/{post_id}", response_model=DeleteResult, tags=["publishing"])
async def delete_post(post_id: PostId, client: Client) -> DeleteResult:
    return DeleteResult(deleted=await client.delete_post(post_id))
