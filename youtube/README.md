# YouTube upload component

One request: send a video and authorized channel credentials to **POST /uploading**.
No API-key header, login endpoint, browser consent flow, saved token store, or upload
lock. The calling main app supplies authorization for the intended channel.

## Run locally

Python 3.11+. From this folder:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api:app --host 127.0.0.1 --port 8001
```

Open http://127.0.0.1:8001/docs, expand POST /uploading, and select:

- `file`: the video.
- `channel_credentials`: an authorized-user OAuth JSON file with `client_id`,
  `client_secret`, and `refresh_token`. Existing `token` and `expiry` are optional.

These are the only required inputs. Title defaults to the original filename stem;
privacy defaults to private. Description, tags, privacy, and made_for_kids are optional.
The upload goes to the channel associated with the supplied OAuth authorization.
A Google client-secret file alone is not channel authorization: the main app must
obtain user consent with the youtube.upload scope and provide the refresh token.
Expired access tokens are refreshed in memory. Credentials are never persisted or
returned by this component. Invalid authorization must be renewed by the calling app.

```python
import requests

with open("clip.mp4", "rb") as video, open("channel-credentials.json", "rb") as creds:
    response = requests.post(
        "http://127.0.0.1:8001/uploading",
        files={"file": ("clip.mp4", video, "video/mp4"),
               "channel_credentials": ("channel.json", creds, "application/json")},
        timeout=(10, 7200),
    )
response.raise_for_status()
print(response.json())
```

Success returns HTTP 201 with video_id, url, status, and message. YouTube processing
may still be pending. The service does not delete uploaded videos.

File and metadata validation remain in the uploader. MAX_VIDEO_BYTES defaults to
2 GiB and can be configured through the environment. Temporary video copies and
upload streams are closed on success and failure. FastAPI runs the synchronous
endpoint in its worker pool; each request creates its own Google client.

This is an internal component without its own authentication or request-header
validation. The main app/deployment owns authentication, HTTPS, request-size limits,
and concurrency limits. Multipart parsing happens before endpoint validation;
configure ingress limits before remote deployment. There is no durable queue or
idempotency handling; check the channel before retrying an ambiguous failure.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
```

Tests mock Google uploads and token refresh. They do not upload or delete videos.
