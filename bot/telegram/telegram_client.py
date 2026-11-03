"""Small Telegram Bot API client."""

import httpx


class TelegramError(Exception):
    """Raised when Telegram rejects a request or the network fails."""


class TelegramClient:
    def __init__(
        self,
        bot_token: str,
        api_url: str = "https://api.telegram.org",
        timeout: float = 15.0,
    ):
        token = (bot_token or "").strip()
        if not token:
            raise TelegramError("BOT_TOKEN is missing.")

        self._base_url = f"{api_url.rstrip('/')}/bot{token}"
        self._http = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.close()

    async def close(self):
        await self._http.aclose()

    async def call(self, method: str, payload: dict | None = None):
        try:
            response = await self._http.post(
                f"{self._base_url}/{method}", json=payload or {}
            )
        except httpx.HTTPError as exc:
            raise TelegramError(
                f"Network error while calling {method} ({type(exc).__name__})."
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramError(
                f"Telegram {method} returned a non-JSON response "
                f"(HTTP {response.status_code})."
            ) from exc

        if not isinstance(data, dict):
            raise TelegramError(
                f"Telegram {method} returned an unexpected response "
                f"(HTTP {response.status_code})."
            )

        if not data.get("ok"):
            code = data.get("error_code", response.status_code)
            description = data.get("description", "Unknown error")
            retry_after = (data.get("parameters") or {}).get("retry_after")
            message = f"Telegram {method} failed ({code}): {description}."
            if retry_after:
                message += f" Retry after {retry_after}s."
            raise TelegramError(message)

        return data.get("result")
