"""Pin the settings tests rely on, so a filled-in repo .env can't change them.

load_dotenv() never overrides variables that are already set, so these win.
"""

import os

os.environ.update({
    "YOUTUBE_URL": "http://127.0.0.1:8001",
    "X_URL": "http://127.0.0.1:8000",
    "TELEGRAM_URL": "http://127.0.0.1:8002",
    "FACEBOOK_URL": "http://127.0.0.1:8003",
    "INSTAGRAM_URL": "http://127.0.0.1:8004",
    "DISCORD_URL": "http://127.0.0.1:8005",
    "YOUTUBE_CREDENTIALS_JSON": "",
    "YOUTUBE_CLIENT_ID": "",
    "YOUTUBE_CLIENT_SECRET": "",
    "YOUTUBE_REFRESH_TOKEN": "",
})
