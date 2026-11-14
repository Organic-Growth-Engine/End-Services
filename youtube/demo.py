"""Local demonstration launcher; main-app integration is intentionally separate."""
import argparse
from getpass import getpass
import logging
import secrets

import uvicorn

import config
from youtube_uploader import TOKEN, credentials


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect YouTube and start the local upload demo.")
    parser.add_argument("--login", action="store_true", help="Reconnect the YouTube account.")
    args = parser.parse_args()

    try:
        if args.login or not TOKEN.exists():
            config.CLIENT_ID = config.CLIENT_ID or input("Google OAuth desktop client ID: ").strip()
            config.CLIENT_SECRET = config.CLIENT_SECRET or getpass("Google OAuth client secret: ").strip()
            credentials(interactive=True)
        else:
            credentials()
    except Exception:
        parser.exit(1, "YouTube authorization failed. Check your OAuth setup and run python demo.py --login.\n")

    # A temporary local-demo key; normal service startup still requires configuration.
    config.UPLOAD_API_SECRET = config.UPLOAD_API_SECRET or secrets.token_urlsafe(32)
    print(f"Open http://127.0.0.1:{config.PORT}/docs")
    print("Expand POST /uploading, click Try it out, and choose your video.")
    print(f"X-API-Key for this demo: {config.UPLOAD_API_SECRET}")
    print("Keep privacy set to private for the first demonstration. Press Ctrl+C to stop.")
    uvicorn.run("api:app", host="127.0.0.1", port=config.PORT, workers=1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
