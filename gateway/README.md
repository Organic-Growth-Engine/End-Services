# Posting gateway

One API that publishes a post to every platform service at once. It converts
the post into each service's own format, calls them all at the same time and
reports the outcome per platform.

```
client ──POST /posts──▶ gateway ──┬──▶ youtube    POST /upload    (:8001)
        ◀── 202 + job id          ├──▶ x          POST /publish   (:8000)
client ──GET /posts/{id}──▶       ├──▶ telegram   POST /publish   (:8002)
                                  ├──▶ facebook   POST /publish   (:8003)
                                  ├──▶ instagram  POST /publish   (:8004)
                                  └──▶ discord    POST /publish   (:8005)
```

## Run everything

From the repo root (see the root README for setup):

```bash
./setup.sh      # once: installs every service, creates .env
./run.sh        # starts every configured service + the gateway on :8080
```

`run.sh` skips services whose credentials aren't in `.env` and tells the
gateway, so those platforms show as `skipped`. A service that is configured
but not running is reported as `failed` ("Could not reach ..."); the others
still post. To turn a platform off, set its URL to empty in `.env`, e.g. `X_URL=`.

To run the gateway on its own: `cd gateway && uv run gateway`.

### YouTube credentials

The gateway sends `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` and
`YOUTUBE_REFRESH_TOKEN` from `.env` with every YouTube upload. A request can
send its own `youtube.credentials` instead, e.g. to post to another channel.

## `POST /posts`

```json
{
  "text": "Launch day\nOur new app is out",
  "media": [{ "type": "video", "url": "https://cdn.example.com/launch.mp4" }],
  "targets": ["youtube", "x", "telegram", "facebook", "instagram", "discord"],
  "x": { "allow_url": false, "made_with_ai": false },
  "telegram": { "parse_mode": "HTML" }
}
```

| Field          | Description                                                                                  |
| -------------- | -------------------------------------------------------------------------------------------- |
| `text`         | Post text. Required unless `media` is set.                                                   |
| `media`        | `type` (`image`, `gif`, `video`, `document`, `audio`), a public direct `url`, optional `alt_text` (X). |
| `targets`      | Platforms to post to. Omit to post everywhere.                                               |
| `title`        | YouTube title. Defaults to the first line of `text` (cut to 100 characters).                 |
| `description`  | YouTube description. Defaults to `text`.                                                     |
| `youtube`      | Optional `credentials` (authorized-user OAuth JSON) overriding the `.env` channel for this request. Never stored or returned. |
| `x`            | `allow_url` (X bills posts with links higher, so they're rejected unless `true`), `made_with_ai`. |
| `telegram`     | `parse_mode`: `HTML`, `Markdown` or `MarkdownV2`.                                            |

The response is `202` with a job. Poll `GET /posts/{id}` until `status` isn't
`running`:

```json
{
  "id": "d1bc5b0e...",
  "status": "partial",
  "targets": {
    "youtube":  { "status": "succeeded", "http_status": 201, "response": { "video_id": "...", "url": "..." } },
    "x":        { "status": "failed", "http_status": 422, "detail": "x service returned HTTP 422.", "response": { "detail": "..." } },
    "telegram": { "status": "skipped", "detail": "..." }
  }
}
```

| Job `status` | Meaning                                         |
| ------------ | ----------------------------------------------- |
| `running`    | Some platforms are still in progress            |
| `succeeded`  | Every platform that was attempted succeeded     |
| `partial`    | Some succeeded, some failed                     |
| `failed`     | Nothing was published                           |
| `skipped`    | No platform could take this post (see `detail`) |

Each platform's `response` is that service's own response body.

### Skipped platforms

A platform is `skipped` (not called) when the post can't go there:

- **YouTube**: no credentials (in `.env` or the request), not exactly one `video`, or no title.
- **X**: the post has `document` or `audio` media.
- **Facebook**: `document`/`audio` media, or a video mixed with other media
  (a Facebook post is text, a link, photos, or one video).
- **Instagram**: no media, or media other than `image`/`video`.
- Any platform whose URL is empty in the configuration.

Instagram only publishes a single feed video as a reel, so one `video` goes to
Instagram as a reel; inside a carousel it stays a video. Discord takes every
media type: images become embeds and other files are posted as links.

Everything else, such as X's 280-character limit or Telegram's caption
length, is checked by the service itself and shows up as `failed` with the
service's message in `response`.

## Things to know

- **Jobs live in memory.** They're lost when the gateway restarts and aren't
  shared between processes, so run a single worker. Replace `JobStore` with a
  database or the event bus when the scheduler is built.
- **No automatic retries.** Publishing isn't idempotent: retrying after a
  timeout could post twice. Retry by sending a new request with `targets` set
  to the platforms that failed.
- **Timeouts.** YouTube downloads and uploads the whole video inside one call,
  so it gets `YOUTUBE_TIMEOUT` (default 2 h); the others get `DEFAULT_TIMEOUT`
  (300 s). A timeout means the post may still have gone out.
- **Trusted callers only.** There's no authentication yet, and the services
  download whatever media URLs they're given. Keep the gateway and services
  on an internal network.

## Tests

```bash
uv run pytest
```

The services are faked with `httpx.MockTransport`, so nothing is posted.
