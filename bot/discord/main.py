"""Discord client factory for the parent application's async lifecycle."""

import asyncio
import logging
import os
from pathlib import Path

import disnake
from disnake.ext import commands

if __package__:
    from .error_handler import ErrorHandler
    from .publisher import Publisher
else:
    from error_handler import ErrorHandler
    from publisher import Publisher


def create_bot():
    """Create on the same running loop that will start and close this client."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError(
            "Call create_bot() inside the parent's async startup, "
            "on the same event loop that will run bot.start()."
        ) from None
    client = commands.InteractionBot(
        loop=loop,
        intents=disnake.Intents(guilds=True),
        allowed_mentions=disnake.AllowedMentions.none(),
    )
    client.add_cog(Publisher())
    client.add_cog(ErrorHandler())
    return client


async def main():
    """Run slash commands locally; parent integrations use create_bot() instead."""
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / '.env')
    token = os.getenv('BOT_TOKEN', '').strip()
    if not token:
        raise ValueError('Set BOT_TOKEN in .env beside main.py or in your environment.')
    bot = create_bot()

    @bot.event
    async def on_ready():
        logging.info('Connected as %s. Use /publish in Discord.', bot.user)

    try:
        await bot.start(token)
    finally:
        await bot.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
