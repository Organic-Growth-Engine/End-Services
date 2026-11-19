"""Turn a gateway post into each platform service's own request.

Each adapter returns the HTTP call to make, or raises Skip when the post can't
go to that platform (e.g. YouTube without a video). Detailed limits such as
X's 280 characters are left to the services, which already enforce them.
"""

from dataclasses import dataclass, field
from typing import Any

from gateway import config
from gateway.schemas import MediaType, Platform, PostRequest

YOUTUBE_TITLE_LIMIT = 100

TELEGRAM_MEDIA_TYPES = {
    MediaType.IMAGE: "photo",
    MediaType.GIF: "animation",
    MediaType.VIDEO: "video",
    MediaType.DOCUMENT: "document",
    MediaType.AUDIO: "audio",
}
X_MEDIA_TYPES = {MediaType.IMAGE, MediaType.GIF, MediaType.VIDEO}


class Skip(Exception):
    """The post doesn't suit this platform; the reason is the message."""


@dataclass
class ServiceCall:
    path: str
    timeout: float
    json: Any = None
    params: dict[str, str] = field(default_factory=dict)


def youtube(post: PostRequest, job_id: str) -> ServiceCall:
    if post.youtube is None:
        raise Skip("No YouTube credentials supplied (set 'youtube.credentials').")
    videos = [m for m in post.media if m.type == MediaType.VIDEO]
    if len(videos) != 1:
        raise Skip(f"YouTube needs exactly one video; the post has {len(videos)}.")

    title = post.title
    if title is None:
        first_line = next((ln.strip() for ln in (post.text or "").splitlines() if ln.strip()), "")
        title = first_line[:YOUTUBE_TITLE_LIMIT]
    if not title.strip():
        raise Skip("YouTube needs a title; set 'title' or 'text'.")

    description = post.description if post.description is not None else post.text or ""
    return ServiceCall(
        path="/upload",
        timeout=config.YOUTUBE_TIMEOUT,
        params={
            "url": str(videos[0].url),
            "file_id": job_id,
            "title": title,
            "description": description,
        },
        json=post.youtube.credentials,
    )


def x(post: PostRequest, job_id: str) -> ServiceCall:
    unsupported = sorted({m.type.value for m in post.media} - X_MEDIA_TYPES)
    if unsupported:
        raise Skip(f"X can't post {', '.join(unsupported)} media.")

    body: dict[str, Any] = {
        "text": post.text,
        "media": [m.model_dump(mode="json", exclude_none=True) for m in post.media],
        "allow_url": post.x.allow_url,
        "made_with_ai": post.x.made_with_ai,
    }
    return ServiceCall(
        path="/publish",
        timeout=config.DEFAULT_TIMEOUT,
        json={k: v for k, v in body.items() if v is not None},
    )


def telegram(post: PostRequest, job_id: str) -> ServiceCall:
    body: dict[str, Any] = {
        "id": job_id,
        "content": post.text,
        "parse_mode": post.telegram.parse_mode,
        "media": [
            {"type": TELEGRAM_MEDIA_TYPES[m.type], "url": str(m.url)} for m in post.media
        ],
    }
    return ServiceCall(
        path="/publish",
        timeout=config.DEFAULT_TIMEOUT,
        json={k: v for k, v in body.items() if v is not None},
    )


ADAPTERS = {"youtube": youtube, "x": x, "telegram": telegram}


def build_call(platform: Platform, post: PostRequest, job_id: str) -> ServiceCall:
    if config.SERVICE_URLS.get(platform) is None:
        raise Skip(f"{platform} is disabled in the gateway configuration.")
    return ADAPTERS[platform](post, job_id)
