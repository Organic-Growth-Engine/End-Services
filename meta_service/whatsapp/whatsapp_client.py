from typing import Any, NoReturn, Self

import httpx

DEFAULT_API_BASE_URL = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v27.0"
DEFAULT_TIMEOUT = 120.0

PHONE_FIELDS = (
    "verified_name,display_phone_number,status,"
    "whatsapp_business_manager_messaging_limit"
)
TEMPLATE_FIELDS = "name,status,language,category,parameter_format"

MAX_MEDIA_BYTES = {
    "image": 5 * 1024 * 1024,
    "video": 16 * 1024 * 1024,
    "audio": 16 * 1024 * 1024,
    "document": 100 * 1024 * 1024,
}
DEFAULT_MIME_TYPES = {
    "image": "image/jpeg",
    "video": "video/mp4",
    "audio": "audio/mpeg",
    "document": "application/pdf",
}
DEFAULT_FILENAMES = {
    "image": "media.jpg",
    "video": "media.mp4",
    "audio": "media.mp3",
    "document": "media.pdf",
}


class WhatsAppError(Exception):
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


class WhatsAppClient:
    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        business_account_id: str = "",
        api_version: str = DEFAULT_API_VERSION,
        api_base_url: str = DEFAULT_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        token = (access_token or "").strip()
        if not token:
            raise WhatsAppError("WA_ACCESS_TOKEN is missing.")
        self.phone_number_id = (phone_number_id or "").strip()
        if not self.phone_number_id:
            raise WhatsAppError("WA_PHONE_NUMBER_ID is missing.")
        self.business_account_id = (business_account_id or "").strip()

        self._base_url = f"{api_base_url.rstrip('/')}/{api_version.strip().strip('/')}"
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )
        # A separate client without the Graph token: media URLs may be hosted
        # anywhere, and the access token must never be sent to those hosts.
        self._download_http = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()
        await self._download_http.aclose()

    async def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            response = await self._http.request(
                method, url, json=payload, params=params, data=data, files=files
            )
        except httpx.HTTPError as exc:
            raise WhatsAppError(f"Network error while calling {url}: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            raise WhatsAppError(
                f"WhatsApp {method} {path} returned a non-JSON response"
                f" (HTTP {response.status_code})."
            ) from None

        if response.is_error or (isinstance(body, dict) and body.get("error")):
            self._raise_api_error(method, path, response.status_code, body)

        if not isinstance(body, dict):
            raise WhatsAppError(
                f"WhatsApp {method} {path} returned an unexpected response"
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
        raise WhatsAppError(
            f"WhatsApp {method} {path} failed (HTTP {status}): {message}"
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

    async def get_phone_number(self) -> dict[str, Any]:
        return await self.get(self.phone_number_id, params={"fields": PHONE_FIELDS})

    async def list_templates(
        self, status: str = "APPROVED", limit: int = 100
    ) -> dict[str, Any]:
        if not self.business_account_id:
            raise WhatsAppError(
                "WA_BUSINESS_ACCOUNT_ID is missing; templates cannot be listed."
            )
        params: dict[str, Any] = {"fields": TEMPLATE_FIELDS, "limit": limit}
        if status:
            params["status"] = status
        return await self.get(
            f"{self.business_account_id}/message_templates", params=params
        )

    async def upload_media(
        self,
        url: str,
        media_type: str,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> str:
        max_bytes = MAX_MEDIA_BYTES.get(media_type)
        if max_bytes is None:
            raise ValueError(f"Unsupported media type: {media_type}")

        content = await self._download(url, max_bytes)
        body = await self.call(
            "POST",
            f"{self.phone_number_id}/media",
            data={"messaging_product": "whatsapp"},
            files={
                "file": (
                    (filename or DEFAULT_FILENAMES[media_type]).strip(),
                    content,
                    (mime_type or DEFAULT_MIME_TYPES[media_type]).strip(),
                )
            },
        )
        media_id = str(body.get("id") or "")
        if not media_id:
            raise WhatsAppError(f"WhatsApp did not return a media id for {url}.")
        return media_id

    async def _download(self, url: str, max_bytes: int) -> bytes:
        try:
            async with self._download_http.stream("GET", url) as response:
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise WhatsAppError(
                        f"Media at {url} exceeds the {max_bytes // (1024 * 1024)} MB"
                        " limit for this media type."
                    )
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise WhatsAppError(
                            f"Media at {url} exceeds the"
                            f" {max_bytes // (1024 * 1024)} MB limit for this media type."
                        )
        except httpx.HTTPError as exc:
            raise WhatsAppError(f"Could not download media from {url}: {exc}") from exc
        return bytes(chunks)

    async def send_message(
        self,
        to: str,
        message_type: str,
        content: dict[str, Any],
        callback_data: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": message_type,
            message_type: content,
        }
        if callback_data:
            payload["biz_opaque_callback_data"] = callback_data
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        return await self.post(f"{self.phone_number_id}/messages", payload=payload)
