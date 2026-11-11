import argparse
import json
import mimetypes
import logging
import os
import tempfile
from contextlib import ExitStack
import threading
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config
from error_handler import handle_cli_error

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN = Path(__file__).resolve().parent / "token.json"
LOCK = threading.Lock()
EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpeg", ".mpg", ".m4v", ".wmv", ".flv", ".3gp"}


def save_credentials(creds):
    # Replace atomically so a crash cannot truncate the previously saved token.
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=TOKEN.parent,
                                         prefix=".token-", delete=False) as token_file:
            name = token_file.name
            token_file.write(creds.to_json())
            token_file.flush()
            os.fsync(token_file.fileno())
        os.replace(name, TOKEN)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()


def credentials(interactive=False):
    creds = None
    try:
        if TOKEN.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    except (ValueError, RefreshError) as exc:
        if not interactive:
            raise RuntimeError("Saved authorization is invalid. Run python youtube_uploader.py login again.") from exc
        creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("Run python youtube_uploader.py login first.")
        if not config.CLIENT_ID or not config.CLIENT_SECRET:
            raise ValueError("Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET first.")
        flow = InstalledAppFlow.from_client_config({"installed": {
            "client_id": config.CLIENT_ID, "client_secret": config.CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]}}, SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    save_credentials(creds)
    return creds


def validate(title, description, privacy, tags):
    if not title.strip() or len(title) > 100 or any(c in title for c in "<>"):
        raise ValueError("Title must contain 1-100 characters and no < or >.")
    if len(description.encode("utf-8")) > 5000 or any(c in description for c in "<>"):
        raise ValueError("Description must be at most 5000 UTF-8 bytes and contain no < or >.")
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Privacy must be private, unlisted or public.")
    if sum(len(tag) + (2 if " " in tag else 0) for tag in tags) + max(0, len(tags) - 1) > 500:
        raise ValueError("Combined tags exceed YouTube's 500-character limit.")


def upload_video(file, title, description="", privacy="private", tags=None, made_for_kids=False):
    tags = tags or []
    validate(title, description, privacy, tags)
    path = Path(file).expanduser().resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Choose an existing, nonempty video file.")
    if path.suffix.lower() not in EXTENSIONS:
        raise ValueError("Unsupported video extension. Use MP4, MOV, MKV, WebM or another supported video format.")
    if path.stat().st_size > config.MAX_VIDEO_BYTES:
        raise ValueError("Video exceeds MAX_VIDEO_BYTES.")
    with LOCK, ExitStack() as resources:
        youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
        resources.callback(youtube.close)
        media = MediaFileUpload(str(path), mimetype=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                                chunksize=8 * 1024 * 1024, resumable=True)
        resources.callback(media.stream().close)
        request = youtube.videos().insert(part="snippet,status", body={
            "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "22"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}}, media_body=media)
        result = None
        while result is None:
            progress, result = request.next_chunk(num_retries=5)
            if progress:
                logging.info("Uploading: %.0f%%", progress.progress() * 100)
        return {"video_id": result["id"], "url": f"https://www.youtube.com/watch?v={result['id']}",
                "status": result.get("status", {}), "message": "Uploaded; YouTube may still be processing the video."}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login")
    sub.add_parser("serve")
    upload = sub.add_parser("upload")
    upload.add_argument("file")
    upload.add_argument("--title", required=True)
    upload.add_argument("--description", default="")
    upload.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    upload.add_argument("--tags", default="")
    upload.add_argument("--made-for-kids", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "login":
            credentials(interactive=True)
            print("Connected. Future uploads reuse token.json.")
        elif args.command == "serve":
            import uvicorn
            uvicorn.run("api:app", host=config.HOST, port=config.PORT)
        else:
            print(json.dumps(upload_video(args.file, args.title, args.description, args.privacy,
                                          [t.strip() for t in args.tags.split(",") if t.strip()], args.made_for_kids), indent=2))
    except Exception as exc:
        handle_cli_error(parser, exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
