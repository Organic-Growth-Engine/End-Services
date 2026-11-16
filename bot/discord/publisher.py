"""Publish media/captions to text channels in servers owned by the caller."""

import asyncio
import io
import logging
from contextlib import closing

import disnake
from aiohttp import ClientError
from disnake.ext import commands

if __package__:
    from .api_server import MAX_UPLOAD
else:
    from api_server import MAX_UPLOAD

logger = logging.getLogger(__name__)
SEND_ERRORS = (disnake.HTTPException, ClientError, asyncio.TimeoutError, OSError)


class Publisher(commands.Cog):
    @commands.slash_command(description="Publish to all text channels in servers you own where this bot is installed.")
    @commands.guild_only()
    @commands.max_concurrency(1, per=commands.BucketType.user, wait=False)
    async def publish(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message: str = commands.Param(default=None, max_length=2000),
        media: disnake.Attachment = None,
    ):
        if not (message and message.strip()) and media is None:
            raise commands.BadArgument("Provide a caption, a media file, or both.")
        guilds = [g for g in inter.bot.guilds if g.owner_id == inter.author.id]
        if not guilds:
            raise commands.CheckFailure("The bot must be installed in a server you own.")
        if media is not None and media.size > MAX_UPLOAD:
            raise commands.BadArgument("Media must be at most 24 MiB.")
        await inter.response.defer(ephemeral=True)
        data = await media.read() if media is not None else None
        if data is not None and len(data) > MAX_UPLOAD:
            raise commands.BadArgument("Media must be at most 24 MiB.")
        sent = skipped = 0
        for guild in guilds:
            for channel in list(guild.text_channels):
                # Recheck ownership in case it changed while an earlier send awaited.
                permissions = channel.permissions_for(guild.me)
                if (guild.owner_id != inter.author.id or not permissions.view_channel
                        or not permissions.send_messages
                        or (data is not None and (not permissions.attach_files
                                                 or len(data) > guild.filesize_limit))):
                    skipped += 1
                    continue
                kwargs = dict(content=message or None, allowed_mentions=disnake.AllowedMentions.none())
                try:
                    if data is None:
                        await channel.send(**kwargs)
                    else:
                        with io.BytesIO(data) as stream:
                            with closing(disnake.File(stream, filename=media.filename)) as file:
                                await channel.send(**kwargs, file=file)
                    sent += 1
                except SEND_ERRORS:
                    logger.warning("Delivery failed or unconfirmed in channel %s", channel.id)
                    skipped += 1
        summary = f"Published to {sent} channel(s). Skipped, failed or unconfirmed: {skipped}."
        if skipped:
            summary += " Check Discord before retrying."
        logger.info("Publish result: %s", summary)
        try:
            await inter.edit_original_response(content=summary)
        except SEND_ERRORS:
            logger.warning("Publishing finished but confirmation failed: %s", summary)
            try:
                await inter.followup.send(summary + " Check Discord before repeating.", ephemeral=True)
            except SEND_ERRORS:
                logger.warning("Could not deliver confirmation; result is recorded above.")
