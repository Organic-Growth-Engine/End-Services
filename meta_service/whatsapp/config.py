import os

from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "").strip()
BUSINESS_ACCOUNT_ID = os.getenv("WA_BUSINESS_ACCOUNT_ID", "").strip()

API_VERSION = os.getenv("WA_API_VERSION", "").strip() or "v27.0"
API_BASE_URL = os.getenv("WA_API_BASE_URL", "").strip() or "https://graph.facebook.com"
