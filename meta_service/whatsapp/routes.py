from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query

import config
from publisher import WhatsAppPublisher
from schemas import (
    PhoneProfile,
    PublishRequest,
    PublishResult,
    TemplateSummary,
)
from whatsapp_client import WhatsAppClient

router = APIRouter()


async def get_client() -> AsyncIterator[WhatsAppClient]:
    async with WhatsAppClient(
        config.ACCESS_TOKEN,
        config.PHONE_NUMBER_ID,
        business_account_id=config.BUSINESS_ACCOUNT_ID,
        api_version=config.API_VERSION,
        api_base_url=config.API_BASE_URL,
    ) as client:
        yield client


Client = Annotated[WhatsAppClient, Depends(get_client)]


async def get_publisher(client: Client) -> WhatsAppPublisher:
    return WhatsAppPublisher(client)


Publisher = Annotated[WhatsAppPublisher, Depends(get_publisher)]


@router.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/phone-number", response_model=PhoneProfile, tags=["account"])
async def get_phone_number(client: Client) -> PhoneProfile:
    body = await client.get_phone_number()
    return PhoneProfile(
        id=str(body.get("id") or "") or None,
        verified_name=body.get("verified_name"),
        display_phone_number=body.get("display_phone_number"),
        status=body.get("status"),
        messaging_limit=body.get("whatsapp_business_manager_messaging_limit"),
    )


@router.get("/templates", response_model=list[TemplateSummary], tags=["account"])
async def get_templates(
    client: Client,
    status: str = "APPROVED",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[TemplateSummary]:
    body = await client.list_templates(status=status, limit=limit)
    return [
        TemplateSummary(
            id=str(item.get("id") or ""),
            name=item.get("name") or "",
            language=item.get("language") or "",
            category=item.get("category"),
            status=item.get("status"),
            parameter_format=item.get("parameter_format"),
        )
        for item in body.get("data") or []
        if item.get("id")
    ]


@router.post("/publish", response_model=PublishResult, tags=["publishing"])
async def publish(post: PublishRequest, publisher: Publisher) -> PublishResult:
    return await publisher.publish(post.model_dump(mode="json", exclude_none=True))
