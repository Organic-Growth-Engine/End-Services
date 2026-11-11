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
