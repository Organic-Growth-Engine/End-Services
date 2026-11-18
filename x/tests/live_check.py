"""Check the service against the real X API with the credentials in .env.

    uv run live_check.py            # account lookup only
    uv run live_check.py --thread   # also post a 2-post thread, then delete it

Each paid step asks for confirmation first. Costs are from
https://docs.x.com/x-api/getting-started/pricing (they can change; the Developer
Console shows current rates).
"""

import argparse
import asyncio
from datetime import UTC, datetime

import config
from publisher import ThreadError, XPublisher
from schemas import PublishRequest
from x_client import XClient, XError


def confirm(question: str) -> bool:
    return input(f"{question} [y/N] ").strip().lower() == "y"


async def main(thread: bool) -> None:
    client = XClient(
        config.API_KEY,
        config.API_SECRET,
        config.ACCESS_TOKEN,
        config.ACCESS_TOKEN_SECRET,
        base_url=config.API_BASE_URL,
        timeout=config.REQUEST_TIMEOUT,
    )

    if not confirm("Look up the authenticated account (about $0.01)?"):
        return
    me = await client.get_me()
    print(f"OK: authenticated as @{me.get('username')} (id {me.get('id')}).")

    if not thread:
        return
    if not confirm(
        f"Post a 2-post thread to @{me.get('username')} and then delete it"
        " (about $0.03 to post plus about $0.02 to delete)?"
    ):
        return

    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    request = PublishRequest(
        text=f"End-Services X publisher check, {stamp}. 1/2",
        thread=[{"text": f"Reply to own post, {stamp}. 2/2"}],
    )
    published = []
    try:
        result = await XPublisher(client).publish(request)
        published = result.posts
        print("OK: thread posted; replying to your own post is allowed.")
    except ThreadError as exc:
        published = exc.published
        print(f"Thread reply was refused: {exc}")
    finally:
        for post in published:
            deleted = await client.delete_post(post.id)
            print(f"Deleted {post.id}: {deleted}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--thread", action="store_true", help="also test a 2-post thread"
    )
    try:
        asyncio.run(main(parser.parse_args().thread))
    except XError as exc:
        raise SystemExit(f"X API error: {exc}") from exc
