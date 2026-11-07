"""Publish text, a single media item or an album to a Telegram chat."""

from telegram import (
    Bot,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

SUPPORTED_MEDIA_TYPES = {"photo", "video", "document", "audio", "animation"}
ALBUM_MEDIA_TYPES = SUPPORTED_MEDIA_TYPES - {"animation"}
TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
MAX_ALBUM_SIZE = 10

SINGLE_MEDIA_METHODS = {
    "photo": "send_photo",
    "video": "send_video",
    "document": "send_document",
    "audio": "send_audio",
    "animation": "send_animation",
}

ALBUM_MEDIA_CLASSES = {
    "photo": InputMediaPhoto,
    "video": InputMediaVideo,
    "document": InputMediaDocument,
    "audio": InputMediaAudio,
}


class TelegramPublisher:
    def __init__(self, bot: Bot):
        self._bot = bot

    async def publish(
        self,
        chat: int | str,
        content: str | None = None,
        media: list[dict] | None = None,
        parse_mode: str | None = None,
    ):
        """Publish text, a single media item, or an album of media."""
        media = media or []

        if content is not None and not isinstance(content, str):
            raise ValueError("Post content must be a string.")
        if parse_mode is not None and not isinstance(parse_mode, str):
            raise ValueError("Post parse_mode must be a string.")
        if not media:
            if not (content and content.strip()):
                raise ValueError("Post has no content or media.")
            if len(content) > TEXT_LIMIT:
                raise ValueError(
                    f"Post content is {len(content)} characters; Telegram "
                    f"allows at most {TEXT_LIMIT} for text messages."
                )
            return await self._send_text(chat, content, parse_mode)
        if len(media) > MAX_ALBUM_SIZE:
            raise ValueError(
                f"Post has {len(media)} media items; Telegram albums support "
                f"at most {MAX_ALBUM_SIZE}. Split the post into multiple posts."
            )

        if len(media) == 1:
            return await self._send_single_media(chat, media[0], content, parse_mode)
        return await self._send_album(chat, media, content, parse_mode)

    async def _send_text(self, chat_id, content, parse_mode):
        return await self._bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode=parse_mode,
        )

    async def _send_single_media(self, chat_id, item, content, parse_mode):
        _validate_media(item)
        media_type = item["type"]
        media_url = item["url"].strip()

        payload = {
            "chat_id": chat_id,
            media_type: media_url,
        }

        caption = item.get("caption") or content
        if caption:
            _validate_caption(caption)
            payload["caption"] = caption
            item_parse_mode = item.get("parse_mode") or parse_mode
            if item_parse_mode:
                payload["parse_mode"] = item_parse_mode

        method = getattr(self._bot, SINGLE_MEDIA_METHODS[media_type])
        return await method(**payload)

    async def _send_album(self, chat_id, media, content, parse_mode):
        album = []
        for index, item in enumerate(media):
            _validate_media(item)
            if item["type"] not in ALBUM_MEDIA_TYPES:
                raise ValueError(
                    f"Telegram albums do not support {item['type']!r} media; "
                    f"use one of {sorted(ALBUM_MEDIA_TYPES)}."
                )

            # The post's content becomes the caption of the first item unless
            # the item provides its own caption.
            caption = item.get("caption") or (content if index == 0 else None)
            payload = {"media": item["url"].strip()}
            if caption:
                _validate_caption(caption)
                payload["caption"] = caption
                item_parse_mode = item.get("parse_mode") or parse_mode
                if item_parse_mode:
                    payload["parse_mode"] = item_parse_mode

            album.append(ALBUM_MEDIA_CLASSES[item["type"]](**payload))

        return await self._bot.send_media_group(chat_id=chat_id, media=album)


def _validate_media(item):
    if not isinstance(item, dict):
        raise TypeError("Each media item must be an object with 'type' and 'url'.")

    media_type = item.get("type")
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ValueError(
            f"Unsupported media type {media_type!r}; expected one of "
            f"{sorted(SUPPORTED_MEDIA_TYPES)}."
        )

    url = item.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Each media item needs a non-empty 'url'.")

    caption = item.get("caption")
    if caption is not None and not isinstance(caption, str):
        raise ValueError("Media 'caption' must be a string.")

    parse_mode = item.get("parse_mode")
    if parse_mode is not None and not isinstance(parse_mode, str):
        raise ValueError("Media 'parse_mode' must be a string.")


def _validate_caption(caption):
    if len(caption) > CAPTION_LIMIT:
        raise ValueError(
            f"Media caption is {len(caption)} characters; Telegram allows at "
            f"most {CAPTION_LIMIT} characters when the post contains media."
        )
