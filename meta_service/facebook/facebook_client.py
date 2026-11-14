import asyncio
import time
from typing import Any, Self

import httpx

DEFAULT_API_BASE_URL = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v27.0"
DEFAULT_TIMEOUT = 120.0

VIDEO_STATUS_READY = "ready"
VIDEO_STATUS_UPLOAD_FAILED = "upload_failed"
VIDEO_STATUS_ERROR = "error"
VIDEO_STATUS_EXPIRED = "expired"

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_POLL_TIMEOUT = 300.0

VIDEO_STATE_PUBLISHED = "PUBLISHED"


class FacebookError(Exception):
    def __init__(
        self,
        message: str,
        code: int | None = None,
        subcode: int | None = None,
        fbtrace_id: str | None = None,
        error_type: str | None = None,
        http_status: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.fbtrace_id = fbtrace_id
        self.error_type = error_type
        self.http_status = http_status


class FacebookClient:
    def __init__(
        self,
        access_token: str,
        page_id: str,
        api_version: str = DEFAULT_API_VERSION,
        api_base_url: str = DEFAULT_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.access_token = (access_token or "").strip()
        if not self.access_token:
            raise FacebookError("ACCESS_TOKEN is missing.")
        self.page_id = (page_id or "").strip()
        if not self.page_id:
            raise FacebookError("PAGE_ID is missing.")
        self._api_version = api_version.strip().strip("/") or DEFAULT_API_VERSION
        self._base_url = f"{api_base_url.rstrip('/')}/{self._api_version}"
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        try:
            response = await self._http.request(
                method, url, json=payload, params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            raise FacebookError(f"Network error while calling {url}: {exc}") from exc

        if allow_empty and response.is_success and not response.content:
            return {"success": True}

        try:
            body = response.json()
        except ValueError:
            if allow_empty and response.is_success:
                return {"success": True}
            raise FacebookError(
                f"Facebook {method} {url} returned a non-JSON response"
                f" (HTTP {response.status_code}).",
                http_status=response.status_code,
            ) from None

        if response.is_error or (isinstance(body, dict) and body.get("error")):
            self._raise_api_error(method, url, response.status_code, body)

        if not isinstance(body, dict):
            raise FacebookError(
                f"Facebook {method} {url} returned an unexpected response"
                f" (HTTP {response.status_code}).",
                http_status=response.status_code,
            )
        return body

    def _raise_api_error(self, method: str, url: str, status: int, body: Any) -> None:
        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            error = {}
        message = error.get("message") or "Unknown error"
        user_message = error.get("error_user_msg")
        if user_message and user_message != message:
            message = f"{message} ({user_message})"
        code = error.get("code")
        subcode = error.get("error_subcode")
        fbtrace_id = error.get("fbtrace_id")
        error_type = error.get("type")
        raise FacebookError(
            f"Facebook {method} {url} failed (HTTP {status}): {message}"
            f" (type={error_type}, code={code}, subcode={subcode},"
            f" fbtrace_id={fbtrace_id})",
            code=code,
            subcode=subcode,
            fbtrace_id=fbtrace_id,
            error_type=error_type,
            http_status=status,
        )

    async def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        return await self._request(method, url, payload=payload, params=params)

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.call("GET", path, params=params)

    async def post(
        self, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.call("POST", path, payload=payload)

    async def get_page(
        self,
        fields: tuple[str, ...] = (
            "id",
            "name",
            "bio",
            "emails",
            "followers_count",
        ),
    ) -> dict[str, Any]:
        return await self.get(self.page_id, params={"fields": ",".join(fields)})

    async def delete_post(self, post_id: str) -> dict[str, Any]:
        _require_id(post_id, "post_id")
        body = await self.call("DELETE", post_id)
        if body.get("success") is False:
            raise FacebookError(f"Facebook did not delete {post_id}: {body}")
        return body

    async def publish_feed_post(
        self,
        message: str | None = None,
        *,
        link: str | None = None,
        attached_media: list[dict[str, str]] | None = None,
        place_id: str | None = None,
    ) -> dict[str, Any]:
        if not message and not link and not attached_media:
            raise ValueError("A feed post needs a message, a link, or attached media.")
        payload = _omit_empty(
            {
                "message": message,
                "link": link,
                "place": place_id,
            }
        )
        if attached_media:
            payload["attached_media"] = attached_media
        body = await self.post(f"{self.page_id}/feed", payload=payload)
        post_id = _response_id(body, "post")
        return {"post_id": post_id}

    async def publish_photo(
        self,
        image_url: str,
        caption: str | None = None,
        alt_text: str | None = None,
        place_id: str | None = None,
    ) -> dict[str, Any]:
        _require_url(image_url, "image_url")
        payload = _omit_empty(
            {
                "url": image_url,
                "caption": caption,
                "alt_text_custom": alt_text,
                "place": place_id,
            }
        )
        body = await self.post(f"{self.page_id}/photos", payload=payload)
        photo_id = _response_id(body, "photo")
        return {"photo_id": photo_id, "post_id": _optional_id(body.get("post_id"))}

    async def upload_unpublished_photo(
        self,
        image_url: str,
        alt_text: str | None = None,
    ) -> str:
        _require_url(image_url, "image_url")
        payload = _omit_empty(
            {
                "url": image_url,
                "published": False,
                "alt_text_custom": alt_text,
            }
        )
        body = await self.post(f"{self.page_id}/photos", payload=payload)
        return _response_id(body, "photo")

    async def publish_multi_photo_post(
        self,
        photo_ids: list[str],
        message: str | None = None,
        place_id: str | None = None,
    ) -> dict[str, Any]:
        if not photo_ids:
            raise ValueError("A multi-photo post needs at least one photo id.")
        attached_media = [
            {"media_fbid": _require_id(photo_id, "photo_id")} for photo_id in photo_ids
        ]
        return await self.publish_feed_post(
            message,
            attached_media=attached_media,
            place_id=place_id,
        )

    async def publish_video(
        self,
        video_url: str,
        description: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        _require_url(video_url, "video_url")
        payload = _omit_empty(
            {
                "file_url": video_url,
                "description": description,
                "title": title,
            }
        )
        body = await self.post(f"{self.page_id}/videos", payload=payload)
        video_id = _response_id(body, "video")
        return {"video_id": video_id}

    async def get_video_status(self, video_id: str) -> dict[str, Any]:
        _require_id(video_id, "video_id")
        body = await self.get(str(video_id), params={"fields": "status"})
        status = body.get("status")
        if not isinstance(status, dict):
            raise FacebookError(
                f"Facebook did not return a status for video {video_id}."
            )
        return status

    async def wait_for_video(
        self,
        video_id: str,
        interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            status = await self.get_video_status(video_id)
            _raise_video_error(video_id, status)
            if _video_is_ready(status):
                return status
            if time.monotonic() >= deadline:
                raise FacebookError(
                    f"Video {video_id} was still processing after {timeout:g} seconds."
                )
            await asyncio.sleep(interval)

    async def start_reel_upload(self) -> tuple[str, str]:
        body = await self.post(
            f"{self.page_id}/video_reels", payload={"upload_phase": "start"}
        )
        video_id = _optional_id(body.get("video_id"))
        upload_url = str(body.get("upload_url") or "")
        if not video_id or not upload_url:
            raise FacebookError("Facebook did not return a reel upload session.")
        return video_id, upload_url

    async def upload_hosted_video(
        self, upload_url: str, video_url: str
    ) -> dict[str, Any]:
        _require_url(upload_url, "upload_url")
        _require_url(video_url, "video_url")
        body = await self._request(
            "POST",
            upload_url,
            headers={
                "Authorization": f"OAuth {self.access_token}",
                "file_url": video_url,
            },
            allow_empty=True,
        )
        if body.get("success") is False:
            raise FacebookError(f"Facebook rejected the video upload: {body}")
        return body

    async def publish_reel(
        self,
        video_url: str,
        description: str | None = None,
        title: str | None = None,
        place_id: str | None = None,
        is_ai_generated: bool | None = None,
    ) -> dict[str, Any]:
        video_id, upload_url = await self.start_reel_upload()
        await self.upload_hosted_video(upload_url, video_url)
        payload = _omit_empty(
            {
                "video_id": video_id,
                "upload_phase": "finish",
                "video_state": VIDEO_STATE_PUBLISHED,
                "description": description,
                "title": title,
                "place": place_id,
                "is_ai_generated": is_ai_generated,
            }
        )
        body = await self.post(f"{self.page_id}/video_reels", payload=payload)
        if body.get("success") is False:
            raise FacebookError(f"Facebook rejected the reel {video_id}: {body}")
        return {"video_id": video_id, "post_id": _optional_id(body.get("post_id"))}

    async def publish_photo_story(
        self, image_url: str, alt_text: str | None = None
    ) -> dict[str, Any]:
        photo_id = await self.upload_unpublished_photo(image_url, alt_text=alt_text)
        body = await self.post(
            f"{self.page_id}/photo_stories", payload={"photo_id": photo_id}
        )
        return {"photo_id": photo_id, "post_id": _story_post_id(body)}

    async def publish_video_story(
        self,
        video_url: str,
        is_ai_generated: bool | None = None,
    ) -> dict[str, Any]:
        video_id, upload_url = await self.start_video_story_upload()
        await self.upload_hosted_video(upload_url, video_url)
        payload = _omit_empty(
            {
                "video_id": video_id,
                "upload_phase": "finish",
                "is_ai_generated": is_ai_generated,
            }
        )
        body = await self.post(f"{self.page_id}/video_stories", payload=payload)
        if body.get("success") is False:
            raise FacebookError(f"Facebook rejected the video story {video_id}: {body}")
        return {"video_id": video_id, "post_id": _story_post_id(body)}

    async def start_video_story_upload(self) -> tuple[str, str]:
        body = await self.post(
            f"{self.page_id}/video_stories", payload={"upload_phase": "start"}
        )
        video_id = _optional_id(body.get("video_id"))
        upload_url = str(body.get("upload_url") or "")
        if not video_id or not upload_url:
            raise FacebookError("Facebook did not return a video story upload session.")
        return video_id, upload_url


def _omit_empty(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "")}


def _optional_id(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _response_id(body: dict[str, Any], kind: str) -> str:
    object_id = _optional_id(body.get("id"))
    if not object_id:
        raise FacebookError(f"Facebook did not return an id for the {kind}.")
    return object_id


def _story_post_id(body: dict[str, Any]) -> str:
    post_id = _optional_id(body.get("post_id"))
    if not post_id:
        raise FacebookError("Facebook did not return a post id for the story.")
    return post_id


def _require_id(value: Any, name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{name} must be a non-empty string.")
    return text


def _require_url(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty http(s) URL.")
    if not value.startswith(("http://", "https://")):
        raise ValueError(
            f"{name} must be an http(s) URL; Facebook fetches the media itself."
        )
    return value


def _raise_video_error(video_id: str, status: dict[str, Any]) -> None:
    video_status = status.get("video_status")
    if video_status == VIDEO_STATUS_EXPIRED:
        raise FacebookError(f"Video {video_id} expired before it could be published.")
    if video_status in (VIDEO_STATUS_ERROR, VIDEO_STATUS_UPLOAD_FAILED):
        raise FacebookError(f"Video {video_id} failed with status {video_status!r}.")

    for phase_name in ("uploading_phase", "processing_phase", "publishing_phase"):
        phase = status.get(phase_name)
        if not isinstance(phase, dict) or phase.get("status") != "error":
            continue
        error = phase.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        raise FacebookError(
            f"Video {video_id} failed during {phase_name}: {message or 'unknown error'}"
        )


def _video_is_ready(status: dict[str, Any]) -> bool:
    video_status = status.get("video_status")
    if video_status == VIDEO_STATUS_READY:
        return True
    publishing = status.get("publishing_phase")
    if isinstance(publishing, dict):
        if publishing.get("status") == "completed":
            return True
        if publishing.get("publish_status") in ("published", "scheduled", "draft"):
            return True
    return False
