# Facebook Service

A FastAPI service that publishes content to a Facebook Page using the official
[Pages API](https://developers.facebook.com/docs/pages-api/posts) and
[Video API](https://developers.facebook.com/docs/video-api/guides/publishing).
This is the Facebook worker of the social media manager's worker layer.

## Modules

| Module               | Purpose                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `main.py`            | FastAPI app, router registration, `FacebookError` → HTTP 502 handler                        |
| `routes.py`          | HTTP routes and `FacebookClient` / `FacebookPublisher` dependencies                         |
| `schemas.py`         | Pydantic request/response models and publishing limits                                      |
| `config.py`          | Loads `FB_PAGE_ACCESS_TOKEN`, `FB_PAGE_ID`, `FB_API_VERSION`, `FB_API_BASE_URL` from `.env` |
| `facebook_client.py` | `FacebookClient` - thin async client over the Graph API publishing endpoints                |
| `publisher.py`       | `FacebookPublisher` - routes a post to the matching publish flow                            |

## Setup

```bash
uv sync
cp .env.example .env  # then fill in the Page access token and Page id
uv run uvicorn main:app --reload
```

The Page access token must be requested by someone who can perform the
`CREATE_CONTENT` task on the Page and must have the following permissions:

- `pages_manage_posts`
- `pages_read_engagement`
- `pages_show_list`
- `publish_video` when publishing videos

Interactive API docs are available at `http://127.0.0.1:8000/docs`.

## Routes

| Method   | Path              | Purpose                            |
| -------- | ----------------- | ---------------------------------- |
| `GET`    | `/health`         | Health check                       |
| `GET`    | `/page`           | Connected Page profile             |
| `POST`   | `/publish`        | Publish a text, link or media post |
| `DELETE` | `/post/{post_id}` | Delete a Page post, photo or video |

Every publish returns:

```json
{
	"post_ids": ["1234567890_0987654321"],
	"media_ids": ["1234567890"]
}
```

`post_ids` are Page post ids (feed posts or stories). `media_ids` are photo or
video ids. Video and reel posts return their video id in `media_ids` but usually
leave `post_ids` empty, since Facebook does not return a Page post id for those
flows.

## Publishing

`POST /publish` accepts a message, a link, or a `media` list:

```bash
curl -X POST http://127.0.0.1:8000/publish \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "Hello from the social media manager!",
    "media": [
      {"type": "IMAGE", "url": "https://example.com/photo.jpg"}
    ]
  }'
```

Supported media items:

```json
[
	{ "type": "IMAGE", "url": "...", "alt_text": "optional" },
	{ "type": "VIDEO", "url": "...", "title": "optional", "wait": false },
	{
		"type": "REELS",
		"url": "...",
		"title": "optional",
		"description": "overrides the post message",
		"is_ai_generated": false
	},
	{ "type": "STORY_IMAGE", "url": "..." },
	{ "type": "STORY_VIDEO", "url": "...", "is_ai_generated": false }
]
```

- Text-only post: `{"message": "..."}`.
- Link post: `{"message": "...", "link": "https://..."}`; `message` is optional.
- Photo/video/reel posts can omit `message`; `message` becomes the photo
  caption or video/reel description.
- One media item publishes as that media type. Multiple `IMAGE` items publish
  as one multi-photo post. Multiple story items publish as one story each.
- A post cannot mix photo, video, reel, or story media, and cannot combine
  `link` with `media`. Publish different content types separately.
- Stories have no caption.

Validation failures return FastAPI's structured `422` response. Facebook API
failures return `502` with `{"detail": "..."}`.

## Deleting

`DELETE /post/{post_id}` deletes a Page post, photo or video by its id:

```bash
curl -X DELETE http://127.0.0.1:8000/post/1234567890_0987654321
```

```json
{
	"post_id": "1234567890_0987654321",
	"success": true
}
```

## Limits

- Photos: JPEG/BMP/PNG/GIF/TIFF, max 10 MB.
- Multi-photo posts: 2–10 images.
- Feed messages: up to 63,206 characters.
- Reels: 9:16 video, 3–90 seconds, and at most 30 API-published reels per
  rolling 24 hours.
- Video stories: 60 seconds max.
- Unpublished photos and videos used for stories or multi-photo posts expire
  on Facebook after about 24 hours if not published.
- Video processing is asynchronous; set `"wait": true` on a video post only
  when the caller needs to block until processing finishes.
