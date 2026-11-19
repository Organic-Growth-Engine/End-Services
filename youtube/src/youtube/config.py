"""Local file limit; channel credentials are supplied with each upload."""

import os

from dotenv import load_dotenv

# Finds the nearest .env walking up from this file, i.e. the repo-wide one.
load_dotenv()

MAX_VIDEO_BYTES = int(
    os.getenv("YOUTUBE_MAX_VIDEO_BYTES") or os.getenv("MAX_VIDEO_BYTES") or 2 * 1024**3
)
if not 1 <= MAX_VIDEO_BYTES <= 256 * 1024**3:
    raise ValueError("MAX_VIDEO_BYTES must be between 1 byte and 256 GiB.")
