import asyncio
import io
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

def broadcast_channel(guild, needs_attachment=False):
    for channel in [guild.system_channel, *guild.text_channels]:
        if channel is None:
            continue
        permissions = channel.permissions_for(guild.me)
        if (permissions.view_channel and permissions.send_messages and permissions.embed_links
                and (not needs_attachment or permissions.attach_files)):
            return channel
    return None


@commands.slash_command(description="Send an announcement to every server (bot owner only).")
@commands.guild_only()
@commands.is_owner()
async def publish(
    inter: disnake.ApplicationCommandInteraction,
    message: str = commands.Param(min_length=1, max_length=4096),
    title: str = commands.Param(min_length=1, max_length=256),
    thumbnail_url: str = commands.Param(default=None, max_length=2048),
    thumbnail: disnake.Attachment = None,
):
    if not message.strip() or not title.strip():
        raise commands.BadArgument("Message and title cannot be blank.")
    if thumbnail_url and thumbnail:
        raise commands.BadArgument("Choose either a thumbnail file or a URL.")
    if thumbnail_url:
        url = urlparse(thumbnail_url)
        if url.scheme not in ("http", "https") or not url.netloc:
            raise commands.BadArgument("Thumbnail must be a direct HTTP or HTTPS image URL.")
    filename = None
    if thumbnail:
        extension = Path(thumbnail.filename).suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            raise commands.BadArgument("Choose a PNG, JPG, GIF or WebP thumbnail.")
        if thumbnail.size > 25 * 1024 * 1024:
            raise commands.BadArgument("Thumbnail must be at most 25 MiB.")
        filename = "thumbnail" + extension

    await inter.response.defer(ephemeral=True)
    thumbnail_data = await thumbnail.read() if thumbnail else None
    embed = disnake.Embed(title=title, description=message)
    if thumbnail:
        embed.set_thumbnail(url="attachment://" + filename)
    elif thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    sent = 0
    skipped = 0
    for guild in list(inter.bot.guilds):
        channel = broadcast_channel(guild, needs_attachment=thumbnail is not None)
        if channel is None or (thumbnail and len(thumbnail_data) > guild.filesize_limit):
            skipped += 1
            continue
        file = disnake.File(io.BytesIO(thumbnail_data), filename=filename) if thumbnail else None
        try:
            if await send_broadcast(channel, embed, file=file):
                sent += 1
            else:
                skipped += 1
        finally:
            if file is not None:
                file.close()
    await inter.edit_original_response(
        content=f"Broadcast sent to {sent} server(s). Skipped or failed: {skipped}."
    )


async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN is missing from .env")

    client = commands.InteractionBot(
        intents=disnake.Intents.default(),
        allowed_mentions=disnake.AllowedMentions.none(),
    )
    client.add_slash_command(publish)
    client.add_cog(ErrorHandler())

    @client.event
    async def on_ready():
        print(f"Connected as {client.user}")

    await run(
        client, token, os.getenv("API_HOST", "127.0.0.1"),
        int(os.getenv("API_PORT", "8080")),
        api_secret=os.getenv("DISCORD_API_SECRET", ""),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
