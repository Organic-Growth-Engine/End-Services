# Instagram Service

FastAPI service that publishes content to an Instagram professional account
using the official [Instagram Platform](https://developers.facebook.com/docs/instagram-platform/content-publishing)
API.

## Setup

```bash
uv sync
cp .env.example .env  # then fill in the token and account id
uv run uvicorn main:app --reload
```

This service targets the **Instagram API with Unified Login** and the Facebook
Graph API (`https://graph.facebook.com`). It requires a Meta Business portfolio,
a Business Integration System User access token with the `instagram_basic` and
`instagram_content_publish` permissions, and the Instagram professional
account ID. Page-linked setups may also need `pages_read_engagement` and the
`MANAGE` or `CREATE_CONTENT` task on the connected Page.

Interactive docs: <http://127.0.0.1:8000/docs>

## Routes

| Method | Path                | Purpose                         |
| ------ | ------------------- | ------------------------------- |
| GET    | `/health`           | Health check                    |
| GET    | `/account`          | Connected account profile       |
| GET    | `/publishing-limit` | Publishing quota usage          |
| POST   | `/publish`          | Publish one or more media items |

`POST /publish` accepts `caption`, optional `location_id`, and `collaborators`,
plus 1-20 `media` items. Every item requires a `type` and a public `url`; the
remaining fields depend on the type:

| Field           | IMAGE      | VIDEO    | REELS    | STORY_IMAGE | STORY_VIDEO |
| --------------- | ---------- | -------- | -------- | ----------- | ----------- |
| `user_tags`     | optional\* | optional | optional | optional    | optional    |
| `alt_text`      | optional   | -        | -        | -           | -           |
| `thumb_offset`  | -          | optional | optional | -           | -           |
| `cover_url`     | -          | -        | optional | -           | -           |
| `share_to_feed` | -          | -        | optional | -           | -           |
| `audio_name`    | -          | -        | optional | -           | -           |

\* Image tags require both `x` and `y`; story tags may omit them.

A single item publishes as its own type; multiple `IMAGE`/`VIDEO` items publish
as a carousel; multiple story items publish as separate stories. `caption`,
`location_id`, and `collaborators` apply to feed posts and carousels only, and
`collaborators` is not supported on feed videos. Unknown fields are rejected
with a 422.

## Limits

Enforced locally by the schemas:

- Captions: 2,200 characters, 30 hashtags, 20 mentions.
- Alt text: 1,000 characters.
- Collaborators: at most 3.
- Carousels: 2-20 images/videos only (no reels or stories).

Enforced by Instagram:

- Images: JPEG, max 8 MB, aspect ratio 4:5-1.91:1.
- Reels: MOV/MP4, max 300 MB, 3 s-15 min. Story videos: max 60 s.
- 100 published posts per rolling 24 hours - check `/publishing-limit`.
