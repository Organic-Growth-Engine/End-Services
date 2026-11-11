import tempfile
import threading
from starlette.formparsers import MultiPartException
from starlette.exceptions import HTTPException as StarletteHTTPException
from pathlib import Path
from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.routing import APIRoute

import config
from error_handler import handle_upload_errors
from youtube_uploader import EXTENSIONS, TOKEN, upload_video, validate

MAX_VIDEO_BYTES = config.MAX_VIDEO_BYTES
MULTIPART_OVERHEAD_BYTES = 64 * 1024

UPLOAD_SLOT = threading.Lock()

app = FastAPI(title="YouTube AutoUpload", version="1.0")


class UploadRoute(APIRoute):
    def get_route_handler(self):
        parse_and_upload = super().get_route_handler()

        async def handle(request: Request):
            secret = config.UPLOAD_API_SECRET.encode("utf-8")
            supplied_key = request.headers.get("X-API-Key", "").encode("utf-8")
            if not secret:
                raise HTTPException(503, "Set UPLOAD_API_SECRET to enable uploads.")
            if not compare_digest(supplied_key, secret):
                raise HTTPException(401, "Invalid X-API-Key.")

            max_request_bytes = MAX_VIDEO_BYTES + MULTIPART_OVERHEAD_BYTES
            try:
                content_length = int(request.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise HTTPException(400, "Invalid Content-Length.") from exc
            if content_length < 0:
                raise HTTPException(400, "Invalid Content-Length.")
            if content_length > max_request_bytes:
                raise HTTPException(413, "Upload request is too large.")

            total = 0
            exceeded = False

            async def receive():
                nonlocal total, exceeded
                message = await request.receive()
                if message["type"] == "http.request":
                    total += len(message.get("body", b""))
                    if total > max_request_bytes:
                        exceeded = True
                        raise MultiPartException("Upload request is too large.")
                return message

            # Bound the stream before FastAPI parses and spools the multipart body.
            if not UPLOAD_SLOT.acquire(blocking=False):
                raise HTTPException(429, "An upload is already running.", headers={"Retry-After": "30"})
            try:
                bounded = Request(request.scope, receive=receive)
                # Bound field/file counts as well as total bytes, and close all spooled files.
                async with bounded.form(max_files=1, max_fields=6, max_part_size=16 * 1024):
                    return await parse_and_upload(bounded)
            except StarletteHTTPException:
                if exceeded:
                    raise HTTPException(413, "Upload request is too large.")
                raise
            finally:
                UPLOAD_SLOT.release()

        return handle


uploads = APIRouter(route_class=UploadRoute)


@app.get("/health")
def health():
    return {"status": "ok", "token_saved": TOKEN.exists()}


@uploads.post("/upload", status_code=201, openapi_extra={"parameters": [{
    "name": "X-API-Key",
    "in": "header",
    "schema": {"type": "string"},
    "description": "Required for all uploads. Configure UPLOAD_API_SECRET before starting.",
}]})
def upload(file: Annotated[UploadFile, File()], title: Annotated[str, Form()],
           description: Annotated[str, Form()] = "", privacy: Annotated[str, Form()] = "private",
           tags: Annotated[str, Form()] = "", made_for_kids: Annotated[bool, Form()] = False):
    """Send a video and metadata as multipart/form-data. Waits until upload completes."""
    with handle_upload_errors():
        try:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            validate(title, description, privacy, tag_list)
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in EXTENSIONS:
                raise ValueError("Choose a supported video file, such as MP4, MOV, MKV or WebM.")
            with tempfile.TemporaryDirectory(prefix="youtube-upload-") as folder:
                path = Path(folder) / ("video" + suffix)
                total = 0
                with path.open("wb") as out:
                    while chunk := file.file.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_VIDEO_BYTES:
                            raise HTTPException(413, "Video exceeds the upload size limit.")
                        out.write(chunk)
                if total == 0:
                    raise ValueError("Choose a nonempty video file.")
                return upload_video(path, title, description, privacy, tag_list, made_for_kids)
        finally:
            file.file.close()


app.include_router(uploads)
