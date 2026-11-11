import asyncio
import logging
import os
from pathlib import Path

import disnake
from disnake.ext import commands
from dotenv import load_dotenv

from api_server import run
from channel_store import ChannelStore
from error_handler import ErrorHandler
from publisher import Publisher

load_dotenv(Path(__file__).resolve().parent / ".env")


async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN is missing from .env")
    client = commands.InteractionBot(
        intents=disnake.Intents.default(),
        allowed_mentions=disnake.AllowedMentions.none(),
    )
    store = ChannelStore(Path(__file__).resolve().parent / "channels.sqlite3")
    client.add_cog(Publisher(store))
    client.add_cog(ErrorHandler())

    @client.event
    async def on_ready():
        logging.info("Connected as %s", client.user)

    await run(
        client, token, os.getenv("API_HOST", "127.0.0.1"),
        int(os.getenv("API_PORT", "8080")),
        api_secret=os.getenv("DISCORD_API_SECRET", ""),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
