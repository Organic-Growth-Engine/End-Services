import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

import config
from error_handler import handle_upload_errors
from youtube_uploader import UploadResult, upload_video

app = FastAPI(title="YouTube upload component", version="1.0")


def read_channel_credentials(file: UploadFile) -> dict:
    payload = file.file.read(64 * 1024 + 1)
    if len(payload) > 64 * 1024:
        raise ValueError("Channel credentials JSON must be at most 64 KiB.")
    try:
        info = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Channel credentials must be valid JSON.") from exc
    if not isinstance(info, dict):
        raise ValueError("Channel credentials must be a JSON object.")
    return info


def copy_video(file: UploadFile, path: Path) -> None:
    total = 0
    with path.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            total += len(chunk)
            if total > config.MAX_VIDEO_BYTES:
                raise HTTPException(413, "Video exceeds the upload size limit.")
            out.write(chunk)


@app.post("/uploading", status_code=201, response_model=None)
def upload(
    file: Annotated[UploadFile, File()],
    channel_credentials: Annotated[UploadFile, File(description="Authorized-user OAuth JSON containing client_id, client_secret and refresh_token.")],
    title: Annotated[str | None, Form()] = None,
    description: Annotated[str, Form()] = "",
    privacy: Annotated[str, Form()] = "private",
    tags: Annotated[str, Form()] = "",
    made_for_kids: Annotated[bool, Form()] = False,
) -> UploadResult:
    """Supply a video and channel authorization; wait for the uploaded video URL."""
    # FastAPI runs this synchronous endpoint in its worker pool.
    try:
        with handle_upload_errors():
            creds = read_channel_credentials(channel_credentials)
            filename = Path((file.filename or "video").replace("\\", "/")).name
            with tempfile.TemporaryDirectory(prefix="youtube-upload-") as folder:
                path = Path(folder) / ("video" + Path(filename).suffix.lower())
                copy_video(file, path)
                return upload_video(
                    path, creds, title=Path(filename).stem if title is None else title,
                    description=description, privacy=privacy,
                    tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
                    made_for_kids=made_for_kids,
                )
    finally:
        try:
            file.file.close()
        finally:
            channel_credentials.file.close()
