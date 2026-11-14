"""Settings come from the process environment; never commit credentials."""
import os

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
UPLOAD_API_SECRET = os.getenv("UPLOAD_API_SECRET", "")
HOST = os.getenv("UPLOAD_HOST", "127.0.0.1")
PORT = int(os.getenv("UPLOAD_PORT", "8001"))
# A practical local disk limit; never allow more than YouTube's maximum.
MAX_VIDEO_BYTES = int(os.getenv("MAX_VIDEO_BYTES", str(2 * 1024**3)))
if not 1 <= MAX_VIDEO_BYTES <= 256 * 1024**3:
    raise ValueError("MAX_VIDEO_BYTES must be between 1 byte and 256 GiB.")

# Loopback OAuth callback; port 0 selects an available local port.
OAUTH_HOST = os.getenv("YOUTUBE_OAUTH_HOST", "localhost")
OAUTH_PORT = int(os.getenv("YOUTUBE_OAUTH_PORT", "0"))
if OAUTH_HOST not in {"localhost", "127.0.0.1"}:
    raise ValueError("YOUTUBE_OAUTH_HOST must be a loopback host.")
if not 0 <= OAUTH_PORT <= 65535:
    raise ValueError("YOUTUBE_OAUTH_PORT must be between 0 and 65535.")
