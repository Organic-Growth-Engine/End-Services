from typing import Any

from instagram_client import InstagramClient
from schemas import MediaType, PublishResult

CAROUSEL_MEDIA_TYPES = {MediaType.IMAGE, MediaType.VIDEO}


class InstagramPublisher:
    def __init__(self, client: InstagramClient):
        self._client = client

    async def publish(self, post: dict[str, Any]) -> PublishResult:
        media = post["media"]
        if len(media) == 1:
            return await self._publish_single(media[0], post)
        if all(item["type"] in CAROUSEL_MEDIA_TYPES for item in media):
            return await self._publish_carousel(
                media,
                caption=post.get("caption"),
                location_id=post.get("location_id"),
                collaborators=post.get("collaborators"),
            )
        results = [await self._publish_story(item) for item in media]
        return _combine(results)

    async def _publish_image(
        self,
        image_url: str,
        caption: str | None = None,
        alt_text: str | None = None,
        location_id: str | None = None,
        collaborators: list[str] | None = None,
        user_tags: list[dict[str, Any]] | None = None,
    ) -> PublishResult:
        return await self._publish(
            _drop_empty(
                {
                    "image_url": image_url,
                    "caption": caption,
                    "alt_text": alt_text,
                    "location_id": location_id,
                    "collaborators": collaborators,
                    "user_tags": user_tags,
                }
            )
        )

    async def _publish_video(
        self,
        video_url: str,
        caption: str | None = None,
        thumb_offset: int | None = None,
        location_id: str | None = None,
        user_tags: list[dict[str, Any]] | None = None,
    ) -> PublishResult:
        return await self._publish(
            _drop_empty(
                {
                    "media_type": MediaType.VIDEO,
                    "video_url": video_url,
                    "caption": caption,
                    "thumb_offset": thumb_offset,
                    "location_id": location_id,
                    "user_tags": user_tags,
                }
            ),
            wait=True,
        )

    async def _publish_reel(
        self,
        video_url: str,
        caption: str | None = None,
        share_to_feed: bool | None = None,
        cover_url: str | None = None,
        thumb_offset: int | None = None,
        audio_name: str | None = None,
        location_id: str | None = None,
        collaborators: list[str] | None = None,
        user_tags: list[dict[str, Any]] | None = None,
    ) -> PublishResult:
        return await self._publish(
            _drop_empty(
                {
                    "media_type": MediaType.REELS,
                    "video_url": video_url,
                    "caption": caption,
                    "share_to_feed": share_to_feed,
                    "cover_url": cover_url,
                    "thumb_offset": thumb_offset,
                    "audio_name": audio_name,
                    "location_id": location_id,
                    "collaborators": collaborators,
                    "user_tags": user_tags,
                }
            ),
            wait=True,
        )

    async def _publish_story(self, item: dict[str, Any]) -> PublishResult:
        is_video = item["type"] == MediaType.STORY_VIDEO
        fields: dict[str, Any] = {"media_type": "STORIES"}
        fields["video_url" if is_video else "image_url"] = item["url"]
        fields.update(_drop_empty({"user_tags": item.get("user_tags")}))
        return await self._publish(fields, wait=is_video)

    async def _publish_carousel(
        self,
        items: list[dict[str, Any]],
        caption: str | None = None,
        location_id: str | None = None,
        collaborators: list[str] | None = None,
    ) -> PublishResult:
        children = []
        for item in items:
            fields: dict[str, Any] = {"is_carousel_item": True}
            if item["type"] == MediaType.IMAGE:
                fields["image_url"] = item["url"]
                if item.get("alt_text"):
                    fields["alt_text"] = item["alt_text"]
            else:
                fields["media_type"] = MediaType.VIDEO
                fields["video_url"] = item["url"]
                if item.get("thumb_offset") is not None:
                    fields["thumb_offset"] = item["thumb_offset"]
            if item.get("user_tags"):
                fields["user_tags"] = item["user_tags"]
            child_id = await self._client.create_media_container(fields)
            if item["type"] == MediaType.VIDEO:
                await self._client.wait_for_container(child_id)
            children.append(child_id)
        return await self._publish(
            _drop_empty(
                {
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    "caption": caption,
                    "location_id": location_id,
                    "collaborators": collaborators,
                }
            )
        )

    async def _publish_single(
        self, item: dict[str, Any], post: dict[str, Any]
    ) -> PublishResult:
        media_type = item["type"]
        if media_type == MediaType.IMAGE:
            return await self._publish_image(
                item["url"],
                caption=post.get("caption"),
                alt_text=item.get("alt_text"),
                location_id=post.get("location_id"),
                collaborators=post.get("collaborators"),
                user_tags=item.get("user_tags"),
            )
        if media_type == MediaType.VIDEO:
            return await self._publish_video(
                item["url"],
                caption=post.get("caption"),
                thumb_offset=item.get("thumb_offset"),
                location_id=post.get("location_id"),
                user_tags=item.get("user_tags"),
            )
        if media_type == MediaType.REELS:
            return await self._publish_reel(
                item["url"],
                caption=post.get("caption"),
                share_to_feed=item.get("share_to_feed"),
                cover_url=item.get("cover_url"),
                thumb_offset=item.get("thumb_offset"),
                audio_name=item.get("audio_name"),
                location_id=post.get("location_id"),
                collaborators=post.get("collaborators"),
                user_tags=item.get("user_tags"),
            )
        return await self._publish_story(item)

    async def _publish(
        self, fields: dict[str, Any], wait: bool = False
    ) -> PublishResult:
        container_id = await self._client.create_media_container(fields)
        if wait:
            await self._client.wait_for_container(container_id)
        body = await self._client.publish_container(container_id)
        config_issue = body.get("config_issue")
        return PublishResult(
            media_ids=[body["id"]],
            container_ids=[container_id],
            config_issues=[config_issue] if config_issue else [],
        )


def _drop_empty(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "", [])}


def _combine(results: list[PublishResult]) -> PublishResult:
    return PublishResult(
        media_ids=[media_id for result in results for media_id in result.media_ids],
        container_ids=[
            container_id for result in results for container_id in result.container_ids
        ],
        config_issues=[issue for result in results for issue in result.config_issues],
    )
