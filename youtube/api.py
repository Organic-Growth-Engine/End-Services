import tempfile
import threading
from pathlib import Path
from secrets import compare_digest

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

import config
from error_handler import handle_upload_errors
from youtube_uploader import EXTENSIONS, UploadResult, upload_video, validate

MAX_VIDEO_BYTES = config.MAX_VIDEO_BYTES
MULTIPART_OVERHEAD_BYTES = 64 * 1024
# Admission control only: busy requests never wait for a worker thread.
UPLOAD_SLOT = threading.Lock()
app = FastAPI(title="YouTube AutoUpload", version="1.0")


class UploadMetadata(BaseModel):
    title: str
    description: str = ""
    privacy: str = "private"
    tags: str = ""
    made_for_kids: bool = False


def check_upload_headers(request: Request) -> None:
    secret = config.UPLOAD_API_SECRET.encode("utf-8")
    supplied_key = request.headers.get("X-API-Key", "").encode("utf-8")
    if not secret:
        raise HTTPException(503, "Set UPLOAD_API_SECRET to enable uploads.")
    if not compare_digest(supplied_key, secret):
        raise HTTPException(401, "Invalid X-API-Key.")
    try:
        content_length = int(request.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise HTTPException(400, "Invalid Content-Length.") from exc
    if content_length < 0:
        raise HTTPException(400, "Invalid Content-Length.")
    if content_length > MAX_VIDEO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(413, "Upload request is too large.")


def bounded_request(request: Request) -> tuple[Request, dict[str, bool]]:
    total = 0
    state = {"exceeded": False}

    async def receive():
        nonlocal total
        message = await request.receive()
        if message["type"] == "http.request":
            total += len(message.get("body", b""))
            if total > MAX_VIDEO_BYTES + MULTIPART_OVERHEAD_BYTES:
                state["exceeded"] = True
                # Starlette closes partially parsed files for this exception.
                raise MultiPartException("Upload request is too large.")
        return message

    return Request(request.scope, receive=receive), state


def copy_video(file: UploadFile, path: Path) -> None:
    total = 0
    with path.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_VIDEO_BYTES:
                raise HTTPException(413, "Video exceeds the upload size limit.")
            out.write(chunk)
    if total == 0:
        raise ValueError("Choose a nonempty video file.")


def upload_from_file(file: UploadFile, metadata: UploadMetadata) -> UploadResult:
    with handle_upload_errors():
        tag_list = [tag.strip() for tag in metadata.tags.split(",") if tag.strip()]
        validate(metadata.title, metadata.description, metadata.privacy, tag_list)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in EXTENSIONS:
            raise ValueError("Choose a supported video file, such as MP4, MOV, MKV or WebM.")
        with tempfile.TemporaryDirectory(prefix="youtube-upload-") as folder:
            path = Path(folder) / ("video" + suffix)
            copy_video(file, path)
            return upload_video(path, metadata.title, metadata.description,
                                metadata.privacy, tag_list, metadata.made_for_kids)


async def parse_and_upload(request: Request) -> UploadResult:
    bounded, state = bounded_request(request)
    try:
        async with bounded.form(max_files=1, max_fields=6, max_part_size=16 * 1024) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise HTTPException(422, "A video file is required.")
            try:
                metadata = UploadMetadata.model_validate({
                    name: form[name] for name in UploadMetadata.model_fields if name in form
                })
            except ValidationError as exc:
                raise HTTPException(422, "Missing or invalid upload metadata.") from exc
            # Keep synchronous disk and Google calls off the event loop.
            # The form stays open until the worker finishes, including on failure.
            return await run_in_threadpool(upload_from_file, file, metadata)
    except StarletteHTTPException:
        if state["exceeded"]:
            raise HTTPException(413, "Upload request is too large.")
        raise


UPLOAD_SCHEMA = UploadMetadata.model_json_schema()
UPLOAD_SCHEMA["properties"]["file"] = {"type": "string", "format": "binary"}
UPLOAD_SCHEMA["required"].append("file")


@app.post("/uploading", status_code=201, response_model=None, openapi_extra={
    "parameters": [{"name": "X-API-Key", "in": "header", "required": True,
                    "schema": {"type": "string"}}],
    "requestBody": {"required": True, "content": {
        "multipart/form-data": {"schema": UPLOAD_SCHEMA}}},
})
async def upload(request: Request) -> UploadResult:
    """Upload a video and metadata, rejecting overlapping requests before parsing."""
    check_upload_headers(request)
    if not UPLOAD_SLOT.acquire(blocking=False):
        raise HTTPException(429, "An upload is already running.", headers={"Retry-After": "30"})
    try:
        return await parse_and_upload(request)
    finally:
        UPLOAD_SLOT.release()
