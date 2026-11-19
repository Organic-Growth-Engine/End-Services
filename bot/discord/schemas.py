"""Request/response models. Limits from https://discord.com/developers/docs/resources/message."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

CONTENT_LIMIT = 2000
MAX_EMBEDS = 10


class MediaType(StrEnum):
    IMAGE = "image"
    GIF = "gif"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class MediaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MediaType
    url: HttpUrl = Field(description="Public, direct link to the file.")
    alt_text: str | None = Field(default=None, description="Embed title for images.")


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    media: list[MediaItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.content is not None and not self.content.strip():
            self.content = None
        if self.content is None and not self.media:
            raise ValueError("a post needs 'content' or 'media'")
        images = [m for m in self.media if m.type in (MediaType.IMAGE, MediaType.GIF)]
        if len(images) > MAX_EMBEDS:
            raise ValueError(f"a post can show at most {MAX_EMBEDS} images")
        return self


class ChannelResult(BaseModel):
    channel_id: str
    ok: bool
    message_id: str | None = None
    error: str | None = None


class PublishResult(BaseModel):
    published: int
    total: int
    results: list[ChannelResult]
