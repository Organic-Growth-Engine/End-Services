import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import disnake
from disnake.ext import commands
from dotenv import load_dotenv

from error_handler import ErrorHandler, send_broadcast
from api_server import run

load_dotenv(Path(__file__).resolve().parent / ".env")

client = commands.InteractionBot(
    intents=disnake.Intents.default(),
    allowed_mentions=disnake.AllowedMentions.none(),
)
client.add_cog(ErrorHandler())


@client.event
async def on_ready():
    print(f"Connected as {client.user}")


@client.slash_command(description="Publish text or a media attachment to a channel.")
@commands.guild_only()
@commands.default_member_permissions(manage_messages=True)
@commands.has_permissions(manage_messages=True)
async def publish(
    inter: disnake.ApplicationCommandInteraction,
    channel: disnake.TextChannel,
    message: str = commands.Param(default=None, max_length=2000),
    media: disnake.Attachment = None,
):
    if channel.guild.id != inter.guild_id:
        raise commands.BadArgument("Choose a channel in this server.")
    if not (message and message.strip()) and media is None:
        raise commands.BadArgument("Provide a message or a media attachment.")
    user_permissions = channel.permissions_for(inter.author)
    if not (user_permissions.view_channel and user_permissions.send_messages):
        raise commands.CheckFailure("You cannot publish in that channel.")
    permissions = channel.permissions_for(inter.guild.me)
    required = ["view_channel", "send_messages"]
    if media is not None:
        required.append("attach_files")
        if media.size > inter.guild.filesize_limit:
            raise commands.BadArgument("That file exceeds this server's upload limit.")
    missing = [name for name in required if not getattr(permissions, name)]
    if missing:
        raise commands.BotMissingPermissions(missing)
    await inter.response.defer(ephemeral=True)
    if media is None:
        await channel.send(content=message)
    else:
        file = await media.to_file()
        try:
            await channel.send(content=message or None, file=file)
        finally:
            file.close()
    await inter.edit_original_response(content=f"Published to {channel.mention}.")


def broadcast_channel(guild):
    for channel in [guild.system_channel, *guild.text_channels]:
        if channel is None:
            continue
        permissions = channel.permissions_for(guild.me)
        if permissions.view_channel and permissions.send_messages and permissions.embed_links:
            return channel
    return None


@client.slash_command(description="Send an announcement to every server (bot owner only).")
@commands.guild_only()
@commands.is_owner()
async def broadcast(
    inter: disnake.ApplicationCommandInteraction,
    message: str = commands.Param(min_length=1, max_length=4096),
    title: str = commands.Param(min_length=1, max_length=256),
    thumbnail_url: str = commands.Param(max_length=2048),
):
    if not message.strip() or not title.strip():
        raise commands.BadArgument("Message and title cannot be blank.")
    url = urlparse(thumbnail_url)
    if url.scheme not in ("http", "https") or not url.netloc:
        raise commands.BadArgument("Thumbnail must be an HTTP or HTTPS URL.")
    await inter.response.defer(ephemeral=True)
    embed = disnake.Embed(title=title, description=message)
    embed.set_thumbnail(url=thumbnail_url)
    sent = 0
    skipped = 0
    for guild in list(client.guilds):
        channel = broadcast_channel(guild)
        if channel is None or not await send_broadcast(channel, embed):
            skipped += 1
        else:
            sent += 1
    await inter.edit_original_response(
        content=f"Broadcast sent to {sent} server(s). Skipped or failed: {skipped}."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN is missing from .env")
    asyncio.run(run(client, token, os.getenv("API_HOST", "127.0.0.1"),
                    int(os.getenv("API_PORT", "8080"))))
