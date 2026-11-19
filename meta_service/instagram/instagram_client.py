import asyncio
import time
from typing import Any, NoReturn, Self

import httpx

DEFAULT_API_BASE_URL = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v27.0"
DEFAULT_TIMEOUT = 120.0

STATUS_FINISHED = "FINISHED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_PUBLISHED = "PUBLISHED"

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_POLL_TIMEOUT = 300.0


class InstagramError(Exception):
    def __init__(
        self,
        message: str,
        code: int | None = None,
        subcode: int | None = None,
        fbtrace_id: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.fbtrace_id = fbtrace_id


class InstagramClient:
    def __init__(
        self,
        access_token: str,
        user_id: str,
        api_version: str = DEFAULT_API_VERSION,
        api_base_url: str = DEFAULT_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        token = (access_token or "").strip()
        if not token:
            raise InstagramError("ACCESS_TOKEN is missing.")
        self.user_id = (user_id or "").strip()
        if not self.user_id:
            raise InstagramError("USER_ID is missing.")
        self._base_url = f"{api_base_url.rstrip('/')}/{api_version.strip().strip('/')}"
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            response = await self._http.request(
                method, url, json=payload, params=params
            )
        except httpx.HTTPError as exc:
            raise InstagramError(f"Network error while calling {url}: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            raise InstagramError(
                f"Instagram {method} {path} returned a non-JSON response"
                f" (HTTP {response.status_code})."
            ) from None

        if response.is_error or (isinstance(body, dict) and body.get("error")):
            self._raise_api_error(method, path, response.status_code, body)

        if not isinstance(body, dict):
            raise InstagramError(
                f"Instagram {method} {path} returned an unexpected response"
                f" (HTTP {response.status_code})."
            )
        return body

    def _raise_api_error(
        self, method: str, path: str, status: int, body: Any
    ) -> NoReturn:
        error = body.get("error", {}) if isinstance(body, dict) else {}
        message = error.get("message") or "Unknown error"
        code = error.get("code")
        subcode = error.get("error_subcode")
        fbtrace_id = error.get("fbtrace_id")
        raise InstagramError(
            f"Instagram {method} {path} failed (HTTP {status}): {message}"
            f" (code={code}, subcode={subcode}, fbtrace_id={fbtrace_id})",
            code=code,
            subcode=subcode,
            fbtrace_id=fbtrace_id,
        )

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.call("GET", path, params=params)

    async def post(
        self, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.call("POST", path, payload=payload)

    async def get_account(self) -> dict[str, Any]:
        return await self.get(
            self.user_id, params={"fields": "id,username,name,media_count"}
        )

    async def create_media_container(self, fields: dict[str, Any]) -> str:
        if not fields:
            raise ValueError("Container fields must be a non-empty object.")
        body = await self.post(f"{self.user_id}/media", payload=fields)
        container_id = str(body.get("id") or "")
        if not container_id:
            raise InstagramError(
                f"Instagram did not return a container id for fields: {fields}"
            )
        return container_id

    async def get_container_status(self, container_id: str) -> str:
        body = await self.get(container_id, params={"fields": "status_code"})
        status = str(body.get("status_code") or "")
        if not status:
            raise InstagramError(
                f"Instagram did not return a status for container {container_id}."
            )
        return status

    async def wait_for_container(
        self,
        container_id: str,
        interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_POLL_TIMEOUT,
    ) -> str:
        deadline = time.monotonic() + timeout
        while True:
            status = await self.get_container_status(container_id)
            if status == STATUS_IN_PROGRESS:
                if time.monotonic() >= deadline:
                    raise InstagramError(
                        f"Container {container_id} was still {STATUS_IN_PROGRESS}"
                        f" after {timeout:g} seconds."
                    )
                await asyncio.sleep(interval)
                continue
            if status in (STATUS_FINISHED, STATUS_PUBLISHED):
                return status
            raise InstagramError(
                f"Container {container_id} status is {status}; it cannot be published."
            )

    async def publish_container(self, container_id: str) -> dict[str, Any]:
        body = await self.post(
            f"{self.user_id}/media_publish", payload={"creation_id": container_id}
        )
        if not body.get("id"):
            raise InstagramError(
                f"Instagram did not return a media id for container {container_id}."
            )
        return body

    async def get_publishing_limit(self) -> dict[str, Any]:
        return await self.get(
            f"{self.user_id}/content_publishing_limit",
            params={"fields": "quota_usage,config"},
        )
