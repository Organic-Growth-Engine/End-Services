import asyncio
import json
import os
import tempfile
from functools import partial
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from youtube import config
from youtube.error_handler import handle_upload_errors
from youtube.youtube_uploader import (
    EXTENSIONS,
    UploadResult,
    download_video,
    upload_video,
)

app = FastAPI(title="YouTube upload component", version="1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload", status_code=201)
async def upload(
    url: str, file_id: str, credentials: dict[str, Any], title: str, description: str
) -> UploadResult:
    """Download the video at ``url``, upload it to YouTube and return the result."""
    # Keep the URL's extension when it is a known video type: validate_video_file
    # checks it and upload_video derives the upload MIME type from it.
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in EXTENSIONS:
        suffix = ".webm"

    with handle_upload_errors():
        # The directory and the downloaded video are removed on success and failure.
        with tempfile.TemporaryDirectory(prefix="youtube-upload-") as folder:
            file = Path(folder) / f"{uuid4()}{suffix}"
            await asyncio.to_thread(download_video, url, file)
            return await asyncio.to_thread(
                upload_video, file, credentials, title, description
            )


def run() -> None:
    """Entry point for `uv run youtube`; YOUTUBE_HOST/YOUTUBE_PORT override the address."""
    uvicorn.run(
        app,
        host=os.getenv("YOUTUBE_HOST", "127.0.0.1"),
        port=int(os.getenv("YOUTUBE_PORT", "8001")),
    )
