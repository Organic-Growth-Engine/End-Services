import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from googleapiclient.errors import HttpError
from secrets import compare_digest

import config
from youtube_uploader import EXTENSIONS, TOKEN, upload_video, validate

app = FastAPI(title="YouTube AutoUpload", version="1.0")


def authorize(x_api_key: Annotated[str, Header()] = ""):
    if config.UPLOAD_API_SECRET and not compare_digest(x_api_key, config.UPLOAD_API_SECRET):
        raise HTTPException(401, "Invalid X-API-Key.")


@app.get("/health")
def health():
    return {"status": "ok", "token_saved": TOKEN.exists()}


@app.post("/upload", dependencies=[Depends(authorize)])
def upload(file: Annotated[UploadFile, File()], title: Annotated[str, Form()],
           description: Annotated[str, Form()] = "", privacy: Annotated[str, Form()] = "private",
           tags: Annotated[str, Form()] = "", made_for_kids: Annotated[bool, Form()] = False):
    """Send a video and metadata as multipart/form-data. Waits until upload completes."""
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
                    if total > 256 * 1024**3:
                        raise HTTPException(413, "Video exceeds 256 GB.")
                    out.write(chunk)
            return upload_video(path, title, description, privacy, tag_list, made_for_kids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except HttpError as exc:
        raise HTTPException(502, {"message": "YouTube rejected the upload.", "google_status": exc.resp.status,
                                  "reason": exc._get_reason()}) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Upload failed. Check connection and Google authorization; run login again if necessary.") from exc
    finally:
        file.file.close()
