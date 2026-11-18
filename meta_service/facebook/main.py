from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import config
from facebook_client import FacebookError
from routes import router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    config.validate()
    yield


app = FastAPI(
    title="Facebook Publishing Service",
    version="0.1.0",
    description="Publishes content to a Facebook Page.",
    lifespan=lifespan,
)

app.include_router(router)


@app.exception_handler(FacebookError)
async def facebook_error_handler(request: Request, exc: FacebookError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
