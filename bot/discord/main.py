"""Discord client factory for the parent application's async lifecycle."""

import asyncio

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
