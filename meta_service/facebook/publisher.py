from typing import Any

from facebook_client import FacebookClient
from schemas import MediaType, PublishResult


class FacebookPublisher:
    def __init__(self, client: FacebookClient):
        self._client = client

    async def publish(self, post: dict[str, Any]) -> PublishResult:
        media = post.get("media") or []
        message = post.get("message") or ""
        place_id = post.get("place_id")

        if not media:
            if post.get("link"):
                return await self.publish_link(message, post["link"], place_id=place_id)
            return await self.publish_text(message, place_id=place_id)

        if len(media) == 1:
            return await self._publish_single(
                media[0], message=message, place_id=place_id
            )

        if media[0]["type"] == MediaType.IMAGE:
            return await self.publish_photos(media, message=message, place_id=place_id)

        results = [
            await self.publish_story(
                item["url"],
                is_video=item["type"] == MediaType.STORY_VIDEO,
                alt_text=item.get("alt_text"),
                is_ai_generated=item.get("is_ai_generated"),
            )
            for item in media
        ]
        return _combine(results)

    async def publish_text(
        self,
        message: str,
        place_id: str | None = None,
    ) -> PublishResult:
        body = await self._client.publish_feed_post(message, place_id=place_id)
        return _result(post_ids=[body["post_id"]])

    async def publish_link(
        self,
        message: str | None,
        link: str,
        place_id: str | None = None,
    ) -> PublishResult:
        body = await self._client.publish_feed_post(
            message, link=link, place_id=place_id
        )
        return _result(post_ids=[body["post_id"]])

    async def publish_photo(
        self,
        image_url: str,
        caption: str | None = None,
        alt_text: str | None = None,
        place_id: str | None = None,
    ) -> PublishResult:
        body = await self._client.publish_photo(
            image_url,
            caption=caption,
            alt_text=alt_text,
            place_id=place_id,
        )
        return _result(
            post_ids=_ids(body.get("post_id")),
            media_ids=[body["photo_id"]],
        )

    async def publish_photos(
        self,
        items: list[dict[str, Any]],
        message: str | None = None,
        place_id: str | None = None,
    ) -> PublishResult:
        photo_ids = [
            await self._client.upload_unpublished_photo(
                item["url"], alt_text=item.get("alt_text")
            )
            for item in items
        ]
        body = await self._client.publish_multi_photo_post(
            photo_ids, message=message, place_id=place_id
        )
        return _result(post_ids=[body["post_id"]], media_ids=photo_ids)

    async def publish_video(
        self,
        video_url: str,
        description: str | None = None,
        title: str | None = None,
        wait: bool = False,
    ) -> PublishResult:
        body = await self._client.publish_video(
            video_url, description=description, title=title
        )
        if wait:
            await self._client.wait_for_video(body["video_id"])
        return _result(media_ids=[body["video_id"]])

    async def publish_reel(
        self,
        video_url: str,
        description: str | None = None,
        title: str | None = None,
        place_id: str | None = None,
        is_ai_generated: bool | None = None,
    ) -> PublishResult:
        body = await self._client.publish_reel(
            video_url,
            description=description,
            title=title,
            place_id=place_id,
            is_ai_generated=is_ai_generated,
        )
        return _result(
            post_ids=_ids(body.get("post_id")),
            media_ids=[body["video_id"]],
        )

    async def publish_story(
        self,
        url: str,
        *,
        is_video: bool = False,
        alt_text: str | None = None,
        is_ai_generated: bool | None = None,
    ) -> PublishResult:
        if is_video:
            body = await self._client.publish_video_story(
                url, is_ai_generated=is_ai_generated
            )
            media_id = body["video_id"]
        else:
            body = await self._client.publish_photo_story(url, alt_text=alt_text)
            media_id = body["photo_id"]
        return _result(post_ids=[body["post_id"]], media_ids=[media_id])

    async def _publish_single(
        self,
        item: dict[str, Any],
        message: str | None,
        place_id: str | None,
    ) -> PublishResult:
        if item["type"] == MediaType.IMAGE:
            return await self.publish_photo(
                image_url=item["url"],
                caption=message,
                alt_text=item.get("alt_text"),
                place_id=place_id,
            )
        if item["type"] == MediaType.VIDEO:
            return await self.publish_video(
                video_url=item["url"],
                description=item.get("description") or message,
                title=item.get("title"),
                wait=item.get("wait") or False,
            )
        if item["type"] == MediaType.REELS:
            return await self.publish_reel(
                video_url=item["url"],
                description=item.get("description") or message,
                title=item.get("title"),
                place_id=place_id,
                is_ai_generated=item.get("is_ai_generated"),
            )
        return await self.publish_story(
            item["url"],
            is_video=item["type"] == MediaType.STORY_VIDEO,
            alt_text=item.get("alt_text"),
            is_ai_generated=item.get("is_ai_generated"),
        )


def _ids(value: str | None) -> list[str]:
    return [value] if value else []


def _result(
    post_ids: list[str] | None = None,
    media_ids: list[str] | None = None,
) -> PublishResult:
    return PublishResult(post_ids=post_ids or [], media_ids=media_ids or [])


def _combine(results: list[PublishResult]) -> PublishResult:
    return PublishResult(
        post_ids=[item for result in results for item in result.post_ids],
        media_ids=[item for result in results for item in result.media_ids],
    )
