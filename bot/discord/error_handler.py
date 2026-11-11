import logging

import disnake
from disnake.ext import commands

logger = logging.getLogger(__name__)


class ErrorHandler(commands.Cog):
    @commands.Cog.listener()
    async def on_slash_command_error(self, inter, error):
        error = getattr(error, "original", error)
        if isinstance(error, commands.NotOwner):
            message = "Only the bot owner can use this command."
        elif isinstance(error, commands.NoPrivateMessage):
            message = "Use this command in a server."
        elif isinstance(error, commands.MaxConcurrencyReached):
            message = "A broadcast is already running. Wait for it to finish."
        elif isinstance(error, (commands.BadArgument, commands.CheckFailure)):
            message = str(error)
        elif isinstance(error, disnake.Forbidden):
            message = "The bot cannot post in that channel. Check its permissions."
        elif isinstance(error, disnake.HTTPException):
            message = "Discord could not complete the request. Please try again."
        else:
            logger.error("Slash command failed", exc_info=(type(error), error, error.__traceback__))
            message = "Something went wrong. Check the bot's terminal for details."
        if inter.response.is_done():
            await inter.followup.send(message, ephemeral=True)
        else:
            await inter.response.send_message(message, ephemeral=True)
