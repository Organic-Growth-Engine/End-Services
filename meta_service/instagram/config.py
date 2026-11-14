import os

from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
USER_ID = os.getenv("IG_USER_ID", "").strip()
API_VERSION = os.getenv("IG_API_VERSION", "").strip() or "v27.0"
API_BASE_URL = os.getenv("IG_API_BASE_URL", "").strip() or "https://graph.facebook.com"
