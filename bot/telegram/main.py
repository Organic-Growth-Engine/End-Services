"""Run the worker with a sample post and chat."""

import asyncio
import logging

from config import CHAT_ID
from worker import publish_post

SAMPLE_POST = {
    "id": 1,
    "content": "This is the content of post 1",
    "media": [
        {"type": "photo", "url": "https://picsum.photos/seed/post-1/1200/800"},
        {"type": "photo", "url": "https://picsum.photos/seed/post-2/1200/800"},
    ],
}


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = asyncio.run(publish_post(SAMPLE_POST, CHAT_ID))
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
