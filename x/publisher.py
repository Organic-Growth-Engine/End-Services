import mimetypes
import tempfile
from typing import Any, BinaryIO

import httpx

import config
from schemas import (
    MediaItem,
    MediaType,
    PostContent,
    PublishedPost,
    PublishRequest,
    PublishResult,
)
from x_client import XClient, XError

MB = 1024 * 1024

# Size limits and media types from https://docs.x.com/x-api/media/introduction and
# the media_type enum of POST /2/media/upload/initialize.
IMAGE_LIMIT = 5 * MB
GIF_LIMIT = 15 * MB
X_VIDEO_LIMIT = 8 * 1024 * MB

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
GIF_TYPES = {"image/gif"}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/mp2t"}

MEDIA_CATEGORIES = {
    MediaType.IMAGE: "tweet_image",
    MediaType.GIF: "tweet_gif",
    MediaType.VIDEO: "tweet_video",
}

DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, read=120.0)


class ThreadError(XError):
    """A thread stopped part-way; some posts are already live."""

    def __init__(
        self, message: str, published: list[PublishedPost], status: int | None
    ):
        super().__init__(message, status=status)
        self.published = published


class MediaError(ValueError):
    pass


def _limits(media_type: MediaType) -> tuple[int, set[str]]:
    if media_type == MediaType.IMAGE:
        return IMAGE_LIMIT, IMAGE_TYPES
    if media_type == MediaType.GIF:
        return GIF_LIMIT, GIF_TYPES
    return min(config.MAX_VIDEO_BYTES, X_VIDEO_LIMIT), VIDEO_TYPES


def _content_type(response: httpx.Response, url: str) -> str:
    header = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if header and header != "application/octet-stream":
        return header
    guessed, _ = mimetypes.guess_type(url)
    return (guessed or "").lower()


async def download(
    http: httpx.AsyncClient, item: MediaItem
) -> tuple[BinaryIO, int, str]:
    """Stream a media URL into a temporary file, enforcing X's type and size limits."""
    url = str(item.url)
    limit, allowed = _limits(item.type)
    file = tempfile.SpooledTemporaryFile(max_size=GIF_LIMIT)  # noqa: SIM115 - returned to the caller, who closes it
    try:
        async with http.stream("GET", url) as response:
            if response.is_error:
                raise MediaError(
                    f"could not download {url} (HTTP {response.status_code})"
                )
            mime = _content_type(response, url)
            if mime not in allowed:
                raise MediaError(
                    f"{url} is '{mime or 'unknown'}'; {item.type} media must be one of"
                    f" {', '.join(sorted(allowed))}"
                )
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                raise MediaError(f"{url} is larger than the {limit // MB} MB limit")
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise MediaError(f"{url} is larger than the {limit // MB} MB limit")
                file.write(chunk)
    except httpx.HTTPError as exc:
        file.close()
        raise MediaError(f"could not download {url}: {exc}") from exc
    except BaseException:
        file.close()
        raise
    if size == 0:
        file.close()
        raise MediaError(f"{url} is empty")
    file.seek(0)
    return file, size, mime


class XPublisher:
    def __init__(self, client: XClient, http: httpx.AsyncClient | None = None):
        self._client = client
        self._http = http

    async def publish(self, request: PublishRequest) -> PublishResult:
        posts: list[PostContent] = [request, *request.thread]

        # Upload every file before creating any post, so a bad file can't leave
        # a half-published (and already billed) thread behind.
        async with self._http_client() as http:
            media_ids = [await self._upload_all(http, post.media) for post in posts]

        published: list[PublishedPost] = []
        for index, (post, ids) in enumerate(zip(posts, media_ids)):
            body = self._body(request, post, ids, index, published)
            try:
                created = await self._client.create_post(body)
            except XError as exc:
                if not published:
                    raise
                raise ThreadError(
                    f"thread stopped at post {index + 1} of {len(posts)}: {exc}",
                    published=published,
                    status=exc.status,
                ) from exc
            published.append(
                PublishedPost(id=created["id"], text=created.get("text", ""))
            )
        return PublishResult(posts=published)

    def _http_client(self):
        if self._http is not None:
            return _Borrowed(self._http)
        return httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)

    async def _upload_all(
        self, http: httpx.AsyncClient, media: list[MediaItem]
    ) -> list[str]:
        ids = []
        for item in media:
            file, size, mime = await download(http, item)
            with file:
                # The docs recommend chunked upload for images, GIFs and video alike.
                media_id = await self._client.upload_chunked(
                    file, size, mime, MEDIA_CATEGORIES[item.type]
                )
            if item.alt_text:
                await self._client.set_alt_text(media_id, item.alt_text)
            ids.append(media_id)
        return ids

    @staticmethod
    def _body(
        request: PublishRequest,
        post: PostContent,
        media_ids: list[str],
        index: int,
        published: list[PublishedPost],
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if post.text:
            body["text"] = post.text
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        if request.made_with_ai is not None:
            body["made_with_ai"] = request.made_with_ai
        if request.paid_partnership is not None:
            body["paid_partnership"] = request.paid_partnership

        if index == 0:
            if request.poll:
                body["poll"] = request.poll.model_dump()
            if request.reply_settings:
                body["reply_settings"] = str(request.reply_settings)
            if request.reply_to_post_id:
                body["reply"] = {"in_reply_to_tweet_id": request.reply_to_post_id}
        else:
            body["reply"] = {"in_reply_to_tweet_id": published[-1].id}
        return body


class _Borrowed:
    """Async context manager that hands back a client without closing it."""

    def __init__(self, http: httpx.AsyncClient):
        self._http = http

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._http

    async def __aexit__(self, *exc) -> None:
        return None
