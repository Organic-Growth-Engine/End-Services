"""Local file limit; channel credentials are supplied with each upload."""
import os

MAX_VIDEO_BYTES = int(os.getenv("MAX_VIDEO_BYTES", str(2 * 1024**3)))
if not 1 <= MAX_VIDEO_BYTES <= 256 * 1024**3:
    raise ValueError("MAX_VIDEO_BYTES must be between 1 byte and 256 GiB.")
