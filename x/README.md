# X (Twitter) Service

FastAPI service that publishes posts, media, polls and threads to an X account
using the [X API v2](https://docs.x.com/x-api/posts/manage-tweets/introduction)
through X's official Python SDK, [`xdk`](https://docs.x.com/xdks/python/overview).

## Setup

1. Sign in at [console.x.com](https://console.x.com), create an app and add
   credits. The X API is [pay-per-use](https://docs.x.com/x-api/getting-started/pricing)
   and has no free plan.
2. Set the app's permissions to **Read and write**, then generate the API key
   and secret and the access token and secret. If you change permissions later,
   generate new access tokens, because old tokens keep their old permissions.

   The user authentication settings also ask for these fields:

   | Field                       | Value                                               |
   | --------------------------- | --------------------------------------------------- |
   | Type of App                 | Web App, Automated App or Bot                       |
   | Callback URI / Redirect URL | `http://127.0.0.1:8000/auth/x/callback` (placeholder) |
   | Website URL                 | Your project's public page, e.g. its GitHub repo    |

   The service doesn't use the callback yet, because it posts with the tokens
   generated in the portal. Use `127.0.0.1`, not `localhost`, which X's docs advise against.
   When "Sign in with X" is added, the callback must exactly match the URL of
   the service's callback route, and the Website URL is shown to users on X's
   consent screen. You can change both later without regenerating tokens.
3. Configure and run:

   ```bash
   uv sync
   cp .env.example .env  # then fill in the four X_* credentials
   uv run uvicorn main:app --reload
   ```

Interactive docs: <http://127.0.0.1:8000/docs>

The service signs requests with OAuth 1.0a user tokens. They don't expire, which
suits an unattended service, and they post as the account that generated them.

## Routes

| Method | Path              | Purpose                                 |
| ------ | ----------------- | --------------------------------------- |
| GET    | `/health`         | Health check                            |
| GET    | `/account`        | The authenticated account (`/2/users/me`) |
| POST   | `/publish`        | Publish a post or a thread              |
| DELETE | `/posts/{id}`     | Delete a post made by this account      |

### `POST /publish`

```json
{
  "text": "Launch day",
  "media": [{ "type": "image", "url": "https://example.com/a.jpg", "alt_text": "Our new app" }],
  "made_with_ai": true,
  "thread": [{ "text": "Here's how it works" }]
}
```

| Field              | Description                                                                 |
| ------------------ | --------------------------------------------------------------------------- |
| `text`             | Post text. Required unless `media` is set.                                  |
| `media`            | Up to 4 `image` items, or 1 `gif`, or 1 `video`. Each has a public `url` and optional `alt_text` (max 1,000 characters). |
| `poll`             | `options` (2-4, each 1-25 characters) and `duration_minutes` (5-10,080).   |
| `reply_to_post_id` | Publish as a reply to this post. See the reply restriction below.           |
| `reply_settings`   | Who can reply: `following`, `mentionedUsers`, `subscribers` or `verified`.  |
| `made_with_ai`     | Disclose AI-generated media.                                                |
| `paid_partnership` | Label the post as a paid promotion.                                         |
| `thread`           | Up to 25 follow-up posts (`text` and `media`), each a reply to the previous one. |
| `allow_url`        | Must be `true` to publish text that contains a URL (see Costs).             |

The response lists the created posts in order: `{"posts": [{"id": "...", "text": "..."}]}`.
Unknown fields are rejected with a 422.

## Limits

Checked by the service before calling X:

- Text is at most 280 **weighted** characters (`X_MAX_POST_LENGTH`), counted
  with [twitter-text](https://docs.x.com/fundamentals/counting-characters):
  emoji and CJK characters count as 2 and every URL counts as 23.
- At most 1 cashtag (`$TICKER`) per post.
- Media: images up to 5 MB (JPEG, PNG, WEBP, GIF), animated GIFs up to 15 MB,
  videos (MP4, MOV, WebM, MPEG-TS) up to `X_MAX_VIDEO_BYTES` (default 512 MB).
  The file type comes from the download's `Content-Type`.

Checked by X:

- Video length is 0.5 seconds to 20 minutes, or 125 minutes for X Premium accounts.
  A video can finish uploading and still be refused when posted, with
  `403 This user is not allowed to post a video longer than N minutes.`
- Rate limits: 100 posts per 15 minutes per user and 10,000 per 24 hours per app.
  A 429 from X is returned as a 429 with `Retry-After`.

All media is uploaded before the first post is created, so a bad file fails the
request without publishing anything. If a later post in a thread fails, the
response is a 502 whose `published` field lists the posts that did go live.

## Self-serve API restrictions

These apply to pay-per-use accounts ([changelog](https://docs.x.com/changelog)):

- **Replies** are only allowed when the original post's author has @mentioned
  your account or quoted one of its posts. This affects `reply_to_post_id`.
  Threads reply to your own posts; run `live_check.py --thread` to confirm that
  X allows this for your account.
- **Quote posts** are not available, so this service doesn't support them.

## Costs

From the [pricing page](https://docs.x.com/x-api/getting-started/pricing) at the
time of writing (the Developer Console shows current rates):

| Action                 | Cost          |
| ---------------------- | ------------- |
| Create a post          | $0.015        |
| Create a post with a URL | $0.20       |
| Alt text (media metadata) | $0.005 per item |

A thread is billed per post. Because URLs cost much more, text containing one
(including a bare domain like `example.com`) is rejected unless `allow_url` is `true`.

## Testing

```bash
uv run pytest
```

The tests mock the X API at the HTTP layer, so they run the real SDK and spend
no credits. To check real credentials, run `uv run live_check.py`, which looks
up the account, or `uv run live_check.py --thread`, which posts a 2-post thread
and deletes it. Both ask before each paid step.

## Notes

- `xdk` is synchronous and sets no network timeout, so the service runs its calls
  in a worker thread and adds `X_REQUEST_TIMEOUT`.
- `twitter-text-parser` imports `pkg_resources`, so `setuptools` is pinned below 81.
- The service downloads media from the URLs it receives. Run it on an internal
  network and only accept requests from trusted callers.
