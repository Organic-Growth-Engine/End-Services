import os

from dotenv import load_dotenv

load_dotenv()


# OAuth 1.0a user-context credentials from the X Developer Console (console.x.com).
API_KEY = os.getenv("X_API_KEY", "").strip()
API_SECRET = os.getenv("X_API_SECRET", "").strip()
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "").strip()
ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()

API_BASE_URL = os.getenv("X_API_BASE_URL", "https://api.x.com")
REQUEST_TIMEOUT = float(os.getenv("X_REQUEST_TIMEOUT", "60"))

# 280 weighted characters for regular accounts. X Premium accounts may post longer text.
MAX_POST_LENGTH = int(os.getenv("X_MAX_POST_LENGTH", "280"))

# Largest video this service will download before uploading. X allows up to 8 GB
# (16 GB with Premium); keep this lower unless the host has the disk for it.
MAX_VIDEO_BYTES = int(os.getenv("X_MAX_VIDEO_BYTES") or 512 * 1024 * 1024)
