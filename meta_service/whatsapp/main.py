from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from routes import router
from whatsapp_client import WhatsAppError

app = FastAPI(
    title="WhatsApp Publishing Service",
    version="0.1.0",
    description="Sends messages to WhatsApp users via the WhatsApp Business Cloud API.",
)

app.include_router(router)


@app.exception_handler(WhatsAppError)
async def whatsapp_error_handler(
    request: Request, exc: WhatsAppError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
