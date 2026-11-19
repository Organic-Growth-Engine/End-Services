# Posting gateway

One API that publishes a post to every platform service at once. It converts
the post into each service's own format, calls them all at the same time and
reports the outcome per platform.

```
client ──POST /posts──▶ gateway ──┬──▶ youtube   POST /upload    (:8001)
        ◀── 202 + job id          ├──▶ x         POST /publish   (:8000)
client ──GET /posts/{id}──▶       └──▶ telegram  POST /publish   (:8002)
```

## Run everything

Each service runs in its own terminal:

```bash
# YouTube (youtube/)
uv run youtube                                   # :8001

# X (x/, on the feature/twitter-service branch) — see x/README.md
uv run uvicorn main:app                          # :8000 by default

# Telegram HTTP API (bot/telegram/; needs BOT_TOKEN and CHAT_IDS in .env)
uv run uvicorn api:app --port 8002

# Gateway (gateway/)
cp .env.example .env                             # optional; defaults match the ports above
uv run --env-file .env gateway                   # :8080, docs at http://127.0.0.1:8080/docs
```

A platform whose service isn't running is reported as `failed` ("Could not
reach ..."); the others still post. To disable one, set its URL to empty in
`.env`, e.g. `X_URL=`.

## `POST /posts`

```json
{
  "text": "Launch day\nOur new app is out",
  "media": [{ "type": "video", "url": "https://cdn.example.com/launch.mp4" }],
  "targets": ["youtube", "x", "telegram"],
  "youtube": { "credentials": { "client_id": "...", "client_secret": "...", "refresh_token": "..." } },
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
| `youtube`      | `credentials`: the channel's authorized-user OAuth JSON. Used for this request only; never stored or returned. |
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

Each platform's `response` is that service's own response body.

### Skipped platforms

A platform is `skipped` (not called) when the post can't go there:

- **YouTube**: no `youtube.credentials`, not exactly one `video`, or no title.
- **X**: the post has `document` or `audio` media.
- Any platform whose URL is empty in the configuration.

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
