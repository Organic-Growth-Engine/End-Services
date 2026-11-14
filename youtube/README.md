# YouTube upload component — demo now, integration later

Python 3.11+ recommended. Accept videos from another app through an HTTP API, or upload directly from the terminal. One connected YouTube account per folder. Credentials are intentionally blank.

## Show an upload now

This is a component intended for later integration with the main app. For now,
run it locally to demonstrate a real upload through POST `/uploading`.
The launcher is only a demo convenience; it does not implement main-app integration.

1. Complete the Google Cloud setup in steps 2–4 below (YouTube Data API enabled,
   OAuth consent/test user configured, and a Desktop app OAuth client created).
2. Open a terminal in the `youtube` folder and run:

   ```powershell
   python -m pip install -r requirements.txt
   python demo.py
   ```

3. On the first run, enter your OAuth client ID and secret when prompted, then
   authorize the intended YouTube account in the browser. Existing environment
   variables are used instead of prompting when available.
4. Open the printed `/docs` URL. Expand **POST /uploading → Try it out**.
5. Paste the printed demo key into **X-API-Key**, select a small video, enter its
   title, leave privacy as **private**, and click **Execute**.
6. A successful upload returns HTTP **201**, `video_id`, and `url`. Open that URL
   while signed into the same YouTube account; video processing may take longer.

The demo binds to localhost with one worker and creates a temporary API key if
none is configured. It does not upload anything until you click Execute.
Use `python demo.py --login` to recover invalid authorization. To switch channels,
back up/remove `token.json` before reconnecting. Stop the demo with Ctrl+C.
Later integration will reuse the upload function or HTTP contract; the main app's
configuration, authentication, and deployment still need to be connected then.

## Setup

1. Open a terminal in this folder: `python -m pip install -r requirements.txt`
2. In https://console.cloud.google.com/ enable **YouTube Data API v3**.
3. Configure Google Auth Platform consent/audience. Add your Google account as a test user while the app is in Testing.
4. Create an **OAuth client ID → Desktop app**. Set its values in the `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` environment variables.
5. Set `UPLOAD_API_SECRET` to a strong random secret before using the HTTP API. Uploads use OAuth; a Google API key is not needed.
6. Run `python youtube_uploader.py login`. Sign in and authorize the intended YouTube channel. This creates `token.json`; keep it private. If authorization expires or is revoked, run login again. If you change OAuth clients or channels, back up and remove the old token before reconnecting.

## Terminal upload

```powershell
python youtube_uploader.py upload "C:\Videos\clip.mp4" --title "My video" --description "My caption" --privacy private --tags "gaming,highlights"
```

Use `--privacy public` or `--privacy unlisted` as needed. Default is private. Add `--made-for-kids` only for content made for children.

## External input API

```powershell
$env:UPLOAD_API_SECRET = "replace-with-a-long-random-secret"
python youtube_uploader.py serve
```

Open http://127.0.0.1:8001/docs to select a file and try POST /uploading. Your other app sends multipart/form-data with `file`, `title`, `description`, `privacy`, comma-separated `tags`, and `made_for_kids` (true/false).

```python
import os
import requests

with open("clip.mp4", "rb") as video:
    response = requests.post(
        "http://127.0.0.1:8001/uploading",
        headers={"X-API-Key": os.environ["UPLOAD_API_SECRET"]},
        files={"file": ("clip.mp4", video, "video/mp4")},
        data={"title": "My video", "description": "Uploaded from my app",
              "privacy": "private", "tags": "gaming,highlights", "made_for_kids": "false"},
        timeout=(10, 7200),
    )
response.raise_for_status()
print(response.json())
```

Install `requests` separately for that example. HTTP 201 success returns video_id, url and YouTube status. Upload completion does not mean YouTube processing is finished.

The API waits for completion and accepts one upload at a time per process. Overlapping requests receive HTTP 429 and `Retry-After: 30` before their files are parsed. Run a single server worker; multi-process deployments require an external queue/lock. Keep the process running; there is no durable queue or restart recovery. Interrupted uploads may need resubmission; check your channel first to avoid duplicates. Multipart bodies are bounded before parsing; at most one file and six fields are accepted. Files are spooled to temporary disk and copied for Google upload, so allow roughly twice the configured video limit in free temporary storage. Files are removed after each request. Extension checks do not guarantee the video codec is valid; YouTube performs final validation. Audio/images alone need conversion to a video first.

## Configuration and safety

Settings are read from environment variables at process startup:

| Variable | Default / purpose |
| --- | --- |
| `YOUTUBE_CLIENT_ID` | OAuth desktop client ID; required for login |
| `YOUTUBE_CLIENT_SECRET` | OAuth desktop client secret; required for login |
| `UPLOAD_API_SECRET` | Required for HTTP uploads; blank disables `/uploading` with 503 |
| `YOUTUBE_OAUTH_HOST` | OAuth callback host: `localhost` or `127.0.0.1`; default `localhost` |
| `YOUTUBE_OAUTH_PORT` | OAuth callback port; `0` chooses an available port |
| `UPLOAD_HOST` | `127.0.0.1` |
| `UPLOAD_PORT` | `8001` |
| `MAX_VIDEO_BYTES` | 2147483648 (2 GiB); configurable up to 256 GiB |

The size limit applies to both CLI and API uploads. Keep the API on localhost,
or put it behind HTTPS and access controls when exposing it remotely. Supply
`X-API-Key` in Swagger's `/uploading` form or your client's headers.

Token updates use atomic replacement. Corrupt or revoked tokens produce a login
instruction; interactive `login` can recover by authorizing again. Keep
`token.json`, OAuth client files, and environment files private and out of Git.
Uploads default to private. Progress is logged to stderr, leaving CLI stdout as
JSON. Google rejection responses do not expose raw upstream error details.

HTTP statuses: 201 uploaded, 400 invalid input, 401 incorrect/missing key,
409 login required, 413 too large, 422 missing/invalid form fields, 429 busy,
502 upstream failure, 503 API secret not configured.

There is no durable queue, restart recovery, or idempotency key. After an ambiguous
failure, check your channel before resubmitting to avoid duplicates. Completion
means YouTube accepted the upload; processing and publishing may still be pending.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
```

Tests mock Google and OAuth; they never upload videos or open a login browser.
The suite was verified locally on Python 3.15.

Google reference: https://developers.google.com/youtube/data/guides/uploading_a_video

POST `/uploading` is the only application endpoint. It handles authentication,
validation, file parsing, and upload through focused helpers. No custom router
or route subclass is used.
Authentication, the busy check, and declared-size checks run before parsing.
Disk copying and Google calls run in the framework thread pool; excess uploads
receive 429 immediately rather than waiting in an upload queue.

Direct callers of `upload_video` must serialize calls that share `token.json`.
Do not run CLI login/upload alongside the server using the same token file.
Atomic replacement prevents partial writes but does not coordinate OAuth refreshes.
Google authorization/token URLs remain standard provider constants. The local OAuth
callback host and port are configurable using the variables above.
