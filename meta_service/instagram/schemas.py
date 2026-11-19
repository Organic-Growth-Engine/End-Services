import re
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)

CAPTION_LIMIT = 2200
HASHTAG_LIMIT = 30
MENTION_LIMIT = 20
ALT_TEXT_LIMIT = 1000
MAX_COLLABORATORS = 3
MAX_MEDIA_ITEMS = 20

_HASHTAG_RE = re.compile(r"#[^\s#]+")
_MENTION_RE = re.compile(r"@[^\s@]+")


def _check_caption_limits(caption: str) -> str:
    hashtags = len(_HASHTAG_RE.findall(caption))
    if hashtags > HASHTAG_LIMIT:
        raise ValueError(
            f"caption has {hashtags} hashtags; Instagram allows at most {HASHTAG_LIMIT}"
        )
    mentions = len(_MENTION_RE.findall(caption))
    if mentions > MENTION_LIMIT:
        raise ValueError(
            f"caption has {mentions} mentions; Instagram allows at most {MENTION_LIMIT}"
        )
    return caption


def _check_usernames(usernames: list[str]) -> list[str]:
    if any(not username.strip() for username in usernames):
        raise ValueError("usernames must be non-empty")
    return usernames


Caption = Annotated[
    str, Field(max_length=CAPTION_LIMIT), AfterValidator(_check_caption_limits)
]
AltText = Annotated[str, Field(max_length=ALT_TEXT_LIMIT)]
Collaborators = Annotated[
    list[str], Field(max_length=MAX_COLLABORATORS), AfterValidator(_check_usernames)
]


class MediaType(StrEnum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    REELS = "REELS"
    STORY_IMAGE = "STORY_IMAGE"
    STORY_VIDEO = "STORY_VIDEO"


class UserTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1)
    x: float | None = Field(default=None, ge=0.0, le=1.0)
    y: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _coordinates_pair(self) -> Self:
        if (self.x is None) != (self.y is None):
            raise ValueError("a user tag needs both 'x' and 'y', or neither")
        return self


class _MediaItemBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    user_tags: list[UserTag] | None = None


class ImageItem(_MediaItemBase):
    type: Literal[MediaType.IMAGE]
    alt_text: AltText | None = None

    @model_validator(mode="after")
    def _tag_coordinates(self) -> Self:
        if self.user_tags and any(tag.x is None for tag in self.user_tags):
            raise ValueError("image user tags require 'x' and 'y'")
        return self


class VideoItem(_MediaItemBase):
    type: Literal[MediaType.VIDEO]
    thumb_offset: int | None = Field(default=None, ge=0)


class ReelItem(_MediaItemBase):
    type: Literal[MediaType.REELS]
    thumb_offset: int | None = Field(default=None, ge=0)
    cover_url: HttpUrl | None = None
    share_to_feed: bool | None = None
    audio_name: str | None = None


class StoryImageItem(_MediaItemBase):
    type: Literal[MediaType.STORY_IMAGE]


class StoryVideoItem(_MediaItemBase):
    type: Literal[MediaType.STORY_VIDEO]


MediaItem = Annotated[
    ImageItem | VideoItem | ReelItem | StoryImageItem | StoryVideoItem,
    Field(discriminator="type"),
]


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: Caption | None = None
    location_id: str | None = None
    collaborators: Collaborators | None = None
    media: list[MediaItem] = Field(min_length=1, max_length=MAX_MEDIA_ITEMS)

    @model_validator(mode="after")
    def _routing(self) -> Self:
        media_types = {item.type for item in self.media}

        if media_types <= {MediaType.STORY_IMAGE, MediaType.STORY_VIDEO}:
            if self.caption is not None:
                raise ValueError("stories do not support 'caption'")
            if self.location_id is not None:
                raise ValueError("stories do not support 'location_id'")
            if self.collaborators is not None:
                raise ValueError("stories do not support 'collaborators'")
            return self

        if len(self.media) > 1:
            if not media_types <= {MediaType.IMAGE, MediaType.VIDEO}:
                raise ValueError(
                    "multiple media must be all IMAGE/VIDEO (carousel) or all"
                    " STORY_IMAGE/STORY_VIDEO"
                )
            return self

        if self.media[0].type == MediaType.VIDEO and self.collaborators is not None:
            raise ValueError("feed videos do not support 'collaborators'")
        return self


class PublishResult(BaseModel):
    media_ids: list[str]
    container_ids: list[str]
    config_issues: list[str] = Field(default_factory=list)


class AccountProfile(BaseModel):
    id: str | None = None
    username: str | None = None
    name: str | None = None
    media_count: int | None = None


class PublishingLimit(BaseModel):
    quota_usage: int
    quota_total: int
    quota_duration: int
