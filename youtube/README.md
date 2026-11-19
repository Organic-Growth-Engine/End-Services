# YouTube upload service

Downloads a video from a URL and uploads it to a YouTube channel. The posting
gateway calls it; you can also call it directly.

## Setup

1. In [Google Cloud Console](https://console.cloud.google.com/), enable
   **YouTube Data API v3** and create an OAuth client of type **Desktop app**.
   Download its JSON. If the OAuth consent screen is in **Testing**, add your
   Google account as a test user.
2. Get a refresh token for the channel:

   ```bash
   uv sync
   uv run python scripts/get_refresh_token.py path/to/client_secret.json
   ```

   Sign in with the account that owns the channel, then paste the three printed
   `YOUTUBE_*` lines into the repo's root `.env`. The gateway sends them with
   each upload.
3. Run it: `./run.sh` from the repo root, or on its own with `uv run youtube`
   (port 8001).

While the consent screen is in **Testing**, Google expires refresh tokens after
7 days; publish the app (or rerun step 2) to keep uploading. Videos uploaded
from an unverified Google Cloud project are locked to private until the project
passes Google's audit.

## `POST /upload`

```bash
curl -X POST 'http://127.0.0.1:8001/upload?url=https://cdn.example.com/clip.mp4&file_id=1&title=Test&description=hello' \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "...", "client_secret": "...", "refresh_token": "..."}'
```

- `url` (query): a public, direct link to the video file, not a web page.
- `file_id`, `title`, `description` (query). The title must be 1–100 characters.
- Body: the channel's OAuth credentials. They are used for this request only,
  refreshed in memory and never stored or returned.

The video is streamed to a temporary folder (at most `YOUTUBE_MAX_VIDEO_BYTES`,
default 2 GiB), uploaded as **private**, and the folder is deleted afterwards
whether the upload worked or not. The file extension, and so the MIME type sent
to YouTube, comes from the URL; unknown extensions default to `.webm`.

| Status | Meaning                                                        |
| ------ | -------------------------------------------------------------- |
| 201    | Uploaded: `video_id`, `url`, `status`, `message`               |
| 400    | Bad URL, failed download, or invalid file/metadata             |
| 409    | The channel authorization is invalid or revoked; reconnect it  |
| 502    | YouTube rejected the upload, or another upstream failure       |

YouTube may still be processing the video after a 201. There's no retry or
idempotency handling: after an unclear failure, check the channel before
uploading again.

This service has no authentication and downloads any URL it's given. Keep it
on an internal network and only accept requests from the gateway.

## Tests

```bash
uv run python -m unittest discover tests
```

Google, the token refresh and the download are mocked; nothing is uploaded.
