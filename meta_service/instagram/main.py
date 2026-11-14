from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from instagram_client import InstagramError
from routes import router

app = FastAPI(
    title="Instagram Publishing Service",
    version="0.1.0",
    description="Publishes content to an Instagram professional account.",
)

app.include_router(router)


@app.exception_handler(InstagramError)
async def instagram_error_handler(
    request: Request, exc: InstagramError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
