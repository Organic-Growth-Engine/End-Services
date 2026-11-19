from typing import Any
from uuid import uuid4

from schemas import (
    MessageReceipt,
    MessageType,
    PublishResult,
    SendFailure,
)
from whatsapp_client import WhatsAppClient, WhatsAppError

MEDIA_TYPES = {
    MessageType.IMAGE,
    MessageType.VIDEO,
    MessageType.AUDIO,
    MessageType.DOCUMENT,
}
CAPTION_TYPES = {
    MessageType.IMAGE,
    MessageType.VIDEO,
    MessageType.DOCUMENT,
}

_WARNINGS = {
    130429: "WhatsApp throughput limit reached; retry with backoff.",
    131030: "Recipient is not in the test allowed list; add it in the Meta app.",
    131047: "Recipient is outside the 24-hour window; use an approved template.",
    132018: "Template components do not match the approved template.",
}


class WhatsAppPublisher:
    def __init__(self, client: WhatsAppClient):
        self._client = client

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        message = request["message"]
        message_type = message["type"]
        media_ids: list[str] = []
        content = await self._build_content(message, media_ids)

        # Internal correlation id attached to each send for provider-side tracing.
        callback_id = uuid4().hex
        receipts: list[MessageReceipt] = []
        failures: list[SendFailure] = []
        warnings: list[str] = []

        for to in request["to"]:
            try:
                body = await self._client.send_message(
                    to,
                    message_type,
                    content,
                    callback_data=f"{callback_id}-{to}",
                    reply_to=request.get("reply_to"),
                )
                receipt = _to_receipt(to, body)
            except WhatsAppError as exc:
                failures.append(
                    SendFailure(
                        to=to,
                        error=str(exc),
                        code=exc.code,
                        subcode=exc.subcode,
                        fbtrace_id=exc.fbtrace_id,
                    )
                )
                warning = _WARNINGS.get(exc.code)
                if warning and warning not in warnings:
                    warnings.append(warning)
                continue
            receipts.append(receipt)

        return PublishResult(
            messages=receipts,
            failures=failures,
            media_ids=media_ids,
            warnings=warnings,
        )

    async def _build_content(
        self, message: dict[str, Any], media_ids: list[str]
    ) -> dict[str, Any]:
        message_type = message["type"]

        if message_type == MessageType.TEXT:
            return {
                "body": message["body"],
                "preview_url": message.get("preview_url", False),
            }

        if message_type == MessageType.TEMPLATE:
            template: dict[str, Any] = {
                "name": message["name"],
                "language": {"code": message["language"]},
            }
            if message.get("components"):
                template["components"] = [
                    {key: value for key, value in component.items() if value is not None}
                    for component in message["components"]
                ]
            return template

        if message_type not in MEDIA_TYPES:
            raise ValueError(f"Unsupported message type: {message_type}")

        if message.get("url"):
            media_id = await self._client.upload_media(
                str(message["url"]),
                message_type,
                filename=message.get("filename"),
                mime_type=message.get("mime_type"),
            )
            media_ids.append(media_id)
            content: dict[str, Any] = {"id": media_id}
        else:
            content = {"id": message["media_id"]}

        if message_type in CAPTION_TYPES and message.get("caption"):
            content["caption"] = message["caption"]
        if message_type == MessageType.DOCUMENT and message.get("filename"):
            content["filename"] = message["filename"]
        return content


def _to_receipt(to: str, body: dict[str, Any]) -> MessageReceipt:
    contacts = body.get("contacts") or []
    messages = body.get("messages") or []
    message = messages[0] if messages else {}
    message_id = str(message.get("id") or "")
    if not message_id:
        raise WhatsAppError(f"WhatsApp did not return a message id for {to}.")

    wa_id = str(contacts[0].get("wa_id") or "") if contacts else ""
    return MessageReceipt(
        to=to,
        wa_id=wa_id or None,
        message_id=message_id,
        message_status=message.get("message_status"),
    )
