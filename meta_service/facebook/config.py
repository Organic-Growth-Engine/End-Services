import os

from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
API_VERSION = os.getenv("FB_API_VERSION", "").strip() or "v27.0"
API_BASE_URL = os.getenv("FB_API_BASE_URL", "").strip() or "https://graph.facebook.com"


def validate() -> None:
    missing = [
        name
        for name, value in (
            ("FB_PAGE_ACCESS_TOKEN", ACCESS_TOKEN),
            ("FB_PAGE_ID", PAGE_ID),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
