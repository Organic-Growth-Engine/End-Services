"""Get a YouTube refresh token for the repo's .env.

1. In Google Cloud Console, enable "YouTube Data API v3", create an OAuth
   client of type "Desktop app" and download its JSON.
2. Run (from youtube/):

       uv run python scripts/get_refresh_token.py path/to/client_secret.json

3. Sign in with the Google account that owns the channel and allow access.
   The script prints three lines to paste into the repo's .env.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    secret_file = Path(sys.argv[1])
    try:
        client = json.loads(secret_file.read_text())
    except (OSError, ValueError) as exc:
        print(f"Can't read {secret_file}: {exc}", file=sys.stderr)
        return 1
    if "installed" not in client:
        print("Use an OAuth client of type 'Desktop app' (the JSON has no 'installed' key).",
              file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_config(client, SCOPES)
    # offline + consent makes Google return a refresh token every time.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("Google returned no refresh token; run the script again.", file=sys.stderr)
        return 1

    print("\nAdd these to the repo's .env:\n")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
