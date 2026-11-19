# Discord Publishing Service

FastAPI service that posts to every configured Discord channel through the
[Discord REST API](https://discord.com/developers/docs/resources/message#create-message).
It's the Discord worker behind the posting gateway.

## Files

| File              | Purpose                                                       |
| ----------------- | ------------------------------------------------------------- |
| `config.py`       | Loads `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_IDS` from the root `.env` |
| `schemas.py`      | Request/response models and Discord limits                    |
| `publisher.py`    | Builds the message and sends it to each channel               |
| `main.py`         | FastAPI app: `POST /publish`, `GET /health`                   |
| `connect_once.py` | One-time Gateway connection Discord requires for new bots     |

## Setup

1. Go to the [Developer Portal](https://discord.com/developers/applications),
   choose **New Application**, open **Bot** and choose **Reset Token**. Copy the token.
2. Invite the bot: **OAuth2 → URL Generator**, select the `bot` scope and the
   **View Channels**, **Send Messages** and **Embed Links** permissions, open the
   generated URL and pick your server.
3. In Discord, enable **Settings → Advanced → Developer Mode**, then right-click
   each destination channel and choose **Copy Channel ID**.
4. Configure, connect once, and run:

   ```bash
   # set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_IDS in the repo's root .env
   uv sync
   uv run python connect_once.py   # only needed once per bot
   uv run uvicorn main:app --port 8005
   ```

Discord requires a bot to connect to its Gateway at least once before it can
send messages over REST. `connect_once.py` does that and exits; the service
itself never holds a Gateway connection.

## `POST /publish`

```json
{
  "content": "Launch day",
  "media": [
    { "type": "image", "url": "https://cdn.example.com/a.jpg", "alt_text": "Our new app" },
    { "type": "video", "url": "https://cdn.example.com/launch.mp4" }
  ]
}
```

| Field     | Description                                                                 |
| --------- | --------------------------------------------------------------------------- |
| `content` | Message text. Required unless `media` is set.                               |
| `media`   | `type` (`image`, `gif`, `video`, `audio`, `document`), a public direct `url`, optional `alt_text`. |

Media is sent by URL, not uploaded, so Discord's file size limit doesn't apply:

- `image` and `gif` become embeds (at most 10). `alt_text` is the embed title.
- `video`, `audio` and `document` links are added to the text, and Discord
  shows its own preview for direct links.
- Text plus links must fit in 2,000 characters.
- Mentions in the text (`@everyone`, roles, users) never ping anyone.

Response, with one result per channel:

```json
{
  "published": 2,
  "total": 2,
  "results": [
    { "channel_id": "111", "ok": true, "message_id": "123", "error": null },
    { "channel_id": "222", "ok": true, "message_id": "124", "error": null }
  ]
}
```

`200` when at least one channel received the post (check `results` for
failures), `502` when every channel failed, `422` for an invalid post.

A `429` rate limit from Discord is retried after its `retry_after` (up to 10 s,
3 attempts), because Discord didn't process that request. Network errors and
timeouts are not retried, since the message may already have been sent.

## Common errors

| Discord error              | Cause                                                    |
| -------------------------- | -------------------------------------------------------- |
| `403: Missing Access`      | The bot isn't in that server or can't see the channel    |
| `403: Missing Permissions` | The bot lacks **Send Messages** / **Embed Links** there  |
| `404: Unknown Channel`     | Wrong id in `DISCORD_CHANNEL_IDS`                        |
| `401: Unauthorized`        | Wrong or reset token                                     |

## Testing

```bash
uv run pytest
```

Discord's API is faked with `httpx.MockTransport`, so nothing is sent.
