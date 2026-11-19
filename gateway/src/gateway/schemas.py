"""The gateway's own post format, and the job records it returns."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Platform = Literal["youtube", "x", "telegram"]
PLATFORMS: tuple[Platform, ...] = ("youtube", "x", "telegram")


class MediaType(StrEnum):
    IMAGE = "image"
    GIF = "gif"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"


class Media(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MediaType
    url: HttpUrl = Field(description="Public, direct link to the file.")
    alt_text: str | None = Field(default=None, description="Used by X.")


class YouTubeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credentials: dict[str, Any] = Field(
        description="Authorized-user OAuth JSON (client_id, client_secret, "
        "refresh_token) for the channel. Never stored or returned."
    )


class XOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_url: bool = Field(
        default=False, description="X bills posts with URLs higher; must opt in."
    )
    made_with_ai: bool | None = None


class TelegramOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parse_mode: Literal["HTML", "Markdown", "MarkdownV2"] | None = None


class PostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, description="Post text / caption.")
    title: str | None = Field(
        default=None, description="YouTube title. Defaults to the first line of text."
    )
    description: str | None = Field(
        default=None, description="YouTube description. Defaults to text."
    )
    media: list[Media] = Field(default_factory=list)
    targets: list[Platform] | None = Field(
        default=None,
        description="Platforms to post to. Omit to post everywhere; platforms "
        "that can't take this post are reported as skipped.",
    )
    youtube: YouTubeOptions | None = None
    x: XOptions = Field(default_factory=XOptions)
    telegram: TelegramOptions = Field(default_factory=TelegramOptions)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.text is not None and not self.text.strip():
            self.text = None
        if self.text is None and not self.media:
            raise ValueError("a post needs 'text' or 'media'")
        if self.targets is not None:
            if not self.targets:
                raise ValueError("'targets' must name at least one platform; omit it for all")
            self.targets = list(dict.fromkeys(self.targets))
        return self


class TargetStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"  # every attempted platform succeeded
    PARTIAL = "partial"  # some succeeded, some failed
    FAILED = "failed"  # nothing was published


class TargetResult(BaseModel):
    status: TargetStatus = TargetStatus.PENDING
    detail: str | None = Field(default=None, description="Why it failed or was skipped.")
    http_status: int | None = Field(default=None, description="The service's status code.")
    response: Any = Field(default=None, description="The service's response body.")
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Job(BaseModel):
    id: str
    status: JobStatus = JobStatus.RUNNING
    created_at: datetime
    finished_at: datetime | None = None
    targets: dict[Platform, TargetResult]
