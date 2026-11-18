"""Request and response models for the X publishing service.

Limits come from the X API docs (docs.x.com) and its OpenAPI spec:
- Create Post: https://docs.x.com/x-api/posts/create-post
- Counting characters: https://docs.x.com/fundamentals/counting-characters
- Media limits: https://docs.x.com/x-api/media/introduction
"""

import re
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from twitter_text import extract_urls, parse_tweet

import config

MAX_IMAGES = 4
ALT_TEXT_LIMIT = 1000
MAX_CASHTAGS = 1
# Not an X limit: caps how many paid posts one request can create.
MAX_THREAD_POSTS = 25

PostId = Annotated[str, Field(pattern=r"^[0-9]{1,19}$")]

# Cashtag pattern from twitter-text: $ followed by 1-6 letters, optional .xx suffix.
_CASHTAG_RE = re.compile(
    r"(?:^|[\s　])\$([a-z]{1,6}(?:[._][a-z]{1,2})?)(?=$|\s|[\W_])",
    re.IGNORECASE,
)


def weighted_length(text: str) -> int:
    return parse_tweet(text).weightedLength


def find_urls(text: str) -> list[str]:
    return extract_urls(text)


class MediaType(StrEnum):
    IMAGE = "image"
    GIF = "gif"
    VIDEO = "video"


class ReplySettings(StrEnum):
    FOLLOWING = "following"
    MENTIONED_USERS = "mentionedUsers"
    SUBSCRIBERS = "subscribers"
    VERIFIED = "verified"


class MediaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MediaType
    url: HttpUrl
    alt_text: str | None = Field(default=None, min_length=1, max_length=ALT_TEXT_LIMIT)


class Poll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    options: list[Annotated[str, Field(min_length=1, max_length=25)]] = Field(
        min_length=2, max_length=4
    )
    duration_minutes: int = Field(ge=5, le=10080)


class PostContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    media: list[MediaItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_content(self) -> Self:
        if self.text is not None and not self.text.strip():
            self.text = None
        if self.text is None and not self.media:
            raise ValueError("a post needs 'text' or 'media'")

        if self.text is not None:
            length = weighted_length(self.text)
            if length > config.MAX_POST_LENGTH:
                raise ValueError(
                    f"text is {length} weighted characters; the limit is"
                    f" {config.MAX_POST_LENGTH} (emoji and CJK count as 2, URLs as 23)"
                )
            cashtags = len(_CASHTAG_RE.findall(self.text))
            if cashtags > MAX_CASHTAGS:
                raise ValueError(
                    f"text has {cashtags} cashtags; X allows {MAX_CASHTAGS} per post"
                )

        types = [item.type for item in self.media]
        if MediaType.GIF in types or MediaType.VIDEO in types:
            if len(types) > 1:
                raise ValueError("a GIF or video must be the only media item in a post")
        elif len(types) > MAX_IMAGES:
            raise ValueError(f"a post can have at most {MAX_IMAGES} images")
        return self


class PublishRequest(PostContent):
    poll: Poll | None = None
    reply_to_post_id: PostId | None = None
    reply_settings: ReplySettings | None = None
    made_with_ai: bool | None = None
    paid_partnership: bool | None = None
    thread: list[PostContent] = Field(default_factory=list, max_length=MAX_THREAD_POSTS)
    allow_url: bool = Field(
        default=False,
        description="Posts containing a URL cost more on X's pay-per-use pricing."
        " They are rejected unless this is true.",
    )

    @model_validator(mode="after")
    def _check_request(self) -> Self:
        if not self.allow_url:
            for index, post in enumerate([self, *self.thread]):
                urls = find_urls(post.text or "")
                if urls:
                    where = "text" if index == 0 else f"thread[{index - 1}].text"
                    raise ValueError(
                        f"{where} contains a URL ({urls[0]}); posts with URLs are billed"
                        " at a higher rate, set 'allow_url' to true to publish anyway"
                    )
        return self


class PublishedPost(BaseModel):
    id: str
    text: str


class PublishResult(BaseModel):
    posts: list[PublishedPost]


class DeleteResult(BaseModel):
    deleted: bool


class AccountProfile(BaseModel):
    id: str
    name: str | None = None
    username: str | None = None
    subscription_type: str | None = None
    verified_type: str | None = None
