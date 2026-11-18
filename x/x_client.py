"""Thin async wrapper around the official X Python SDK (xdk).

xdk is synchronous and sets no network timeout, so every call runs in a worker
thread and the underlying requests session gets a default timeout.
"""

import asyncio
import base64
import time
from typing import Any, BinaryIO

import requests
from pydantic import ValidationError
from requests.adapters import HTTPAdapter
from xdk import Client
from xdk.oauth1_auth import OAuth1

DEFAULT_BASE_URL = "https://api.x.com"
DEFAULT_TIMEOUT = 60.0

# A JSON append body is base64-encoded, which adds a third; the API reference
# says to keep JSON segments at 4 MB or less.
CHUNK_SIZE = 4 * 1024 * 1024

DEFAULT_PROCESSING_TIMEOUT = 600.0


class XError(Exception):
    def __init__(
        self,
        message: str,
        status: int | None = None,
        retry_at: int | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.retry_at = retry_at


class _TimeoutAdapter(HTTPAdapter):
    def __init__(self, timeout: float, **kwargs: Any):
        self._timeout = timeout
        super().__init__(**kwargs)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return super().send(request, **kwargs)


def _describe_error(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or response.reason
    if not isinstance(body, dict):
        return str(body)[:300]
    parts = [body.get("title"), body.get("detail")]
    for error in body.get("errors") or []:
        if isinstance(error, dict):
            parts.append(error.get("message") or error.get("detail"))
    text = "; ".join(str(part) for part in parts if part)
    return text or response.reason


def _check_errors(response: Any, action: str) -> Any:
    data = getattr(response, "data", None)
    if data is None:
        errors = getattr(response, "errors", None) or []
        details = "; ".join(
            str(getattr(e, "detail", None) or getattr(e, "title", None) or e)
            for e in errors
        )
        raise XError(f"X {action} returned no data: {details or 'unknown error'}")
    return data


class XClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        # Checked on first use rather than here, so request validation errors
        # are reported before configuration problems.
        self._missing = [
            name
            for name, value in (
                ("X_API_KEY", api_key),
                ("X_API_SECRET", api_secret),
                ("X_ACCESS_TOKEN", access_token),
                ("X_ACCESS_TOKEN_SECRET", access_token_secret),
            )
            if not value
        ]
        auth = OAuth1(
            api_key=api_key,
            api_secret=api_secret,
            # Required by xdk but only used for the 3-legged flow, not here.
            callback="oob",
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        self._sdk = Client(base_url=base_url.rstrip("/"), auth=auth)
        adapter = _TimeoutAdapter(timeout)
        self._sdk.session.mount("https://", adapter)
        self._sdk.session.mount("http://", adapter)

    async def _call(self, action: str, fn, *args: Any, **kwargs: Any) -> Any:
        if self._missing:
            raise XError(f"Missing credentials: {', '.join(self._missing)}.")
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except requests.HTTPError as exc:
            response = exc.response
            status = response.status_code if response is not None else None
            retry_at = None
            if response is not None and status == 429:
                reset = response.headers.get("x-rate-limit-reset")
                retry_at = int(reset) if reset and reset.isdigit() else None
            detail = _describe_error(response) if response is not None else str(exc)
            raise XError(
                f"X {action} failed (HTTP {status}): {detail}",
                status=status,
                retry_at=retry_at,
            ) from exc
        except requests.RequestException as exc:
            raise XError(f"Network error during X {action}: {exc}") from exc
        except ValidationError as exc:
            raise XError(f"X {action} returned an unexpected response: {exc}") from exc

    async def get_me(self) -> dict[str, Any]:
        response = await self._call(
            "account lookup",
            self._sdk.users.get_me,
            user_fields=[
                "id",
                "name",
                "username",
                "subscription_type",
                "verified_type",
            ],
        )
        return _check_errors(response, "account lookup").model_dump(exclude_none=True)

    async def create_post(self, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._call("create post", self._sdk.posts.create, body)
        return _check_errors(response, "create post").model_dump(exclude_none=True)

    async def delete_post(self, post_id: str) -> bool:
        response = await self._call("delete post", self._sdk.posts.delete, post_id)
        return bool(_check_errors(response, "delete post").deleted)

    async def upload_chunked(
        self,
        file: BinaryIO,
        total_bytes: int,
        media_type: str,
        media_category: str,
        processing_timeout: float = DEFAULT_PROCESSING_TIMEOUT,
    ) -> str:
        """INIT -> APPEND -> FINALIZE -> STATUS (docs: media-upload-chunked)."""
        init = await self._call(
            "upload initialize",
            self._sdk.media.initialize_upload,
            {
                "media_type": media_type,
                "total_bytes": total_bytes,
                "media_category": media_category,
            },
        )
        media_id = _check_errors(init, "upload initialize").id

        segment = 0
        while chunk := file.read(CHUNK_SIZE):
            await self._call(
                "upload append",
                self._sdk.media.append_upload,
                media_id,
                {
                    "media": base64.b64encode(chunk).decode("ascii"),
                    "segment_index": segment,
                },
            )
            segment += 1

        final = await self._call(
            "upload finalize", self._sdk.media.finalize_upload, media_id
        )
        info = _check_errors(final, "upload finalize").processing_info
        await self._wait_for_processing(media_id, info, processing_timeout)
        return media_id

    async def _wait_for_processing(
        self,
        media_id: str,
        info: Any,
        timeout: float = DEFAULT_PROCESSING_TIMEOUT,
    ) -> None:
        # No processing_info means the media is ready to use.
        deadline = time.monotonic() + timeout
        while info is not None and info.state != "succeeded":
            if info.state == "failed":
                raise XError(f"X could not process media {media_id}.")
            if time.monotonic() >= deadline:
                raise XError(
                    f"Media {media_id} was still processing after {timeout:g} seconds."
                )
            await asyncio.sleep(max(info.check_after_secs or 1, 1))
            status = await self._call(
                "upload status",
                self._sdk.media.get_upload_status,
                media_id,
                command="STATUS",
            )
            info = _check_errors(status, "upload status").processing_info

    async def set_alt_text(self, media_id: str, text: str) -> None:
        await self._call(
            "media metadata",
            self._sdk.media.create_metadata,
            {"id": media_id, "metadata": {"alt_text": {"text": text}}},
        )
