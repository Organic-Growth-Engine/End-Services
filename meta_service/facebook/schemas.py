from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, model_validator

MESSAGE_LIMIT = 63206
MAX_PHOTOS = 10


class MediaType(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    REELS = "REELS"
    STORY_IMAGE = "STORY_IMAGE"
    STORY_VIDEO = "STORY_VIDEO"


class MediaItem(BaseModel):
    type: MediaType
    url: HttpUrl
    alt_text: str | None = None
    title: str | None = None
    description: str | None = Field(default=None, max_length=MESSAGE_LIMIT)
    is_ai_generated: bool | None = None
    wait: bool | None = None

    @model_validator(mode="after")
    def _type_options(self) -> "MediaItem":
        if self.alt_text is not None and self.type not in (
            MediaType.IMAGE,
            MediaType.STORY_IMAGE,
        ):
            raise ValueError("'alt_text' is only supported on images and photo stories")
        if self.title is not None and self.type not in (
            MediaType.VIDEO,
            MediaType.REELS,
        ):
            raise ValueError("'title' is only supported on videos and reels")
        if self.description is not None and self.type not in (
            MediaType.VIDEO,
            MediaType.REELS,
        ):
            raise ValueError("'description' is only supported on videos and reels")
        if self.is_ai_generated is not None and self.type not in (
            MediaType.REELS,
            MediaType.STORY_VIDEO,
        ):
            raise ValueError(
                "'is_ai_generated' is only supported on reels and video stories"
            )
        if self.wait is not None and self.type != MediaType.VIDEO:
            raise ValueError("'wait' is only supported on video posts")
        return self


class PublishRequest(BaseModel):
    message: str | None = Field(default=None, max_length=MESSAGE_LIMIT)
    link: HttpUrl | None = None
    place_id: str | None = Field(default=None, min_length=1)
    media: list[MediaItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _content_and_routing(self) -> "PublishRequest":
        if self.media and self.link:
            raise ValueError("a post cannot have both 'link' and 'media'")
        if not self.media:
            if not self.message and not self.link:
                raise ValueError("a post needs a 'message', a 'link', or 'media'")
            return self
        if len(self.media) == 1:
            return self
        media_types = {item.type for item in self.media}
        if media_types == {MediaType.IMAGE}:
            if len(self.media) > MAX_PHOTOS:
                raise ValueError(f"multi-photo posts allow at most {MAX_PHOTOS} images")
            return self
        if media_types <= {MediaType.STORY_IMAGE, MediaType.STORY_VIDEO}:
            return self
        raise ValueError(
            "a post cannot mix photo, video, reel, or story media;"
            " publish them as separate posts"
        )


class PublishResult(BaseModel):
    post_ids: list[str] = Field(default_factory=list)
    media_ids: list[str] = Field(default_factory=list)


class DeleteResult(BaseModel):
    post_id: str
    success: bool = True


class PageProfile(BaseModel):
    id: str | None = None
    name: str | None = None
    bio: str | None = None
    emails: list[str] | None = None
    followers_count: int | None = None
