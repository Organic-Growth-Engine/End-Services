import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from publisher import MediaError, ThreadError
from routes import router
from x_client import XError

app = FastAPI(
    title="X Publishing Service",
    version="0.1.0",
    description="Publishes posts, media, polls and threads to an X account.",
)

app.include_router(router)


@app.exception_handler(XError)
async def x_error_handler(request: Request, exc: XError) -> JSONResponse:
    content: dict = {"detail": str(exc), "x_status": exc.status}
    if isinstance(exc, ThreadError):
        content["published"] = [post.model_dump() for post in exc.published]

    if exc.status == 429:
        headers = {}
        if exc.retry_at:
            headers["Retry-After"] = str(max(int(exc.retry_at - time.time()), 1))
        return JSONResponse(status_code=429, content=content, headers=headers)
    return JSONResponse(status_code=502, content=content)


@app.exception_handler(MediaError)
async def media_error_handler(request: Request, exc: MediaError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})
