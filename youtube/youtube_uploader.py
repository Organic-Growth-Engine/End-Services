import logging
import mimetypes
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.http import MediaFileUpload

import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpeg", ".mpg", ".m4v", ".wmv", ".flv", ".3gp"}


def load_credentials(info: dict[str, Any]) -> Credentials:
    """Use authorized-user credentials supplied by the calling app."""
    required = ("client_id", "client_secret", "refresh_token")
    if not isinstance(info, dict) or any(
        not isinstance(info.get(key), str) or not info[key].strip() for key in required
    ):
        raise ValueError("Channel credentials require client_id, client_secret and refresh_token.")
    # Pass only supported credential fields, never a caller-controlled token URL.
    fields = {key: info[key] for key in (*required, "token", "expiry") if key in info}
    try:
        creds = Credentials.from_authorized_user_info(fields, SCOPES)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid channel credentials JSON.") from exc
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise RuntimeError("Channel authorization is invalid; reconnect it in the calling app.") from exc
    if not creds.valid:
        raise RuntimeError("Channel authorization is invalid; reconnect it in the calling app.")
    return creds


def validate(title: str, description: str, privacy: str, tags: list[str]) -> None:
    if not title.strip() or len(title) > 100 or any(c in title for c in "<>"):
        raise ValueError("Title must contain 1-100 characters and no < or >.")
    if len(description.encode("utf-8")) > 5000 or any(c in description for c in "<>"):
        raise ValueError("Description must be at most 5000 UTF-8 bytes and contain no < or >.")
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Privacy must be private, unlisted or public.")
    if sum(len(tag) + (2 if " " in tag else 0) for tag in tags) + max(0, len(tags) - 1) > 500:
        raise ValueError("Combined tags exceed YouTube's 500-character limit.")


class YouTubeResponse(TypedDict):
    id: str
    status: NotRequired[dict[str, Any]]


class UploadResult(TypedDict):
    video_id: str
    url: str
    status: dict[str, Any]
    message: str


def validate_video_file(file: str | Path) -> Path:
    path = Path(file).expanduser().resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Choose an existing, nonempty video file.")
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError("Unsupported video extension. Use MP4, MOV, MKV, WebM or another supported video format.")
    if path.stat().st_size > config.MAX_VIDEO_BYTES:
        raise ValueError("Video exceeds MAX_VIDEO_BYTES.")
    return path


def upload_video(file: str | Path, channel_credentials: dict[str, Any],
                 title: str | None = None, description: str = "",
                 privacy: str = "private", tags: list[str] | None = None,
                 made_for_kids: bool = False) -> UploadResult:
    """Upload using request-supplied channel authorization; never persist credentials."""
    path = validate_video_file(file)
    title = path.stem if title is None else title
    tags = tags or []
    validate(title, description, privacy, tags)
    youtube_client: Resource = build("youtube", "v3", credentials=load_credentials(channel_credentials), cache_discovery=False)
    try:
        media = MediaFileUpload(str(path), mimetype=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                                chunksize=8 * 1024 * 1024, resumable=True)
        try:
            request = youtube_client.videos().insert(part="snippet,status", body={
                "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "22"},
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}}, media_body=media)
            result: YouTubeResponse | None = None
            while result is None:
                progress, result = request.next_chunk(num_retries=5)
                if progress:
                    logging.info("Uploading: %.0f%%", progress.progress() * 100)
            video_id = result["id"]
            return {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}",
                    "status": result.get("status", {}), "message": "Uploaded; YouTube may still be processing the video."}
        finally:
            media.stream().close()
    finally:
        youtube_client.close()
