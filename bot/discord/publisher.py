"""Guild subscriptions and owner-only announcement delivery."""

import io
import logging
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import disnake
from disnake.ext import commands

logger = logging.getLogger(__name__)
MAX_THUMBNAIL = 25 * 1024 * 1024


def require_guild_owner(inter):
    if inter.guild is None:
        raise commands.NoPrivateMessage()
    if inter.author.id != inter.guild.owner_id:
        raise commands.CheckFailure("Only the server owner can configure announcements.")
    return True


def can_send(channel, *, needs_attachment=False):
    permissions = channel.permissions_for(channel.guild.me)
    return (permissions.view_channel and permissions.send_messages and permissions.embed_links
            and (not needs_attachment or permissions.attach_files))


def broadcast_channel(guild, store, *, needs_attachment=False):
    channel_id = store.get(guild.id)
    channel = guild.get_channel(channel_id) if channel_id is not None else None
    if isinstance(channel, disnake.TextChannel) and can_send(channel, needs_attachment=needs_attachment):
        return channel
    return None


@dataclass(frozen=True)
class Thumbnail:
    url: str | None = None
    filename: str | None = None
    data: bytes | None = None

    @contextmanager
    def open_file(self):
        if self.data is None:
            yield None
            return
        # Disnake File restores the caller-owned stream's close method;
        # the outer context owns and closes the stream itself.
        with io.BytesIO(self.data) as stream:
            with closing(disnake.File(stream, filename=self.filename)) as file:
                yield file


async def prepare_thumbnail(url=None, attachment=None):
    if url and attachment is not None:
        raise commands.BadArgument("Choose either a thumbnail file or a URL.")
    if attachment is not None:
        extension = Path(attachment.filename).suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            raise commands.BadArgument("Choose a PNG, JPG, GIF or WebP thumbnail.")
        if attachment.size > MAX_THUMBNAIL:
            raise commands.BadArgument("Thumbnail must be at most 25 MiB.")
        data = await attachment.read()
        if len(data) > MAX_THUMBNAIL:
            raise commands.BadArgument("Thumbnail must be at most 25 MiB.")
        filename = "thumbnail" + extension
        return Thumbnail("attachment://" + filename, filename, data)
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise commands.BadArgument("Thumbnail must be a direct HTTP or HTTPS image URL.")
    return Thumbnail(url=url)


async def send_broadcast(channel, embed, *, file=None):
    try:
        await channel.send(embed=embed, file=file, allowed_mentions=disnake.AllowedMentions.none())
        return True
    except disnake.HTTPException:
        logger.warning("Broadcast failed in channel %s", channel.id)
        return False


class Publisher(commands.Cog):
    def __init__(self, store):
        self.store = store

    @commands.slash_command(description="Select this server's announcement channel (server owner only).")
    @commands.guild_only()
    @commands.check(require_guild_owner)
    async def publish(self, inter: disnake.ApplicationCommandInteraction, channel: disnake.TextChannel):
        if channel.guild.id != inter.guild.id:
            raise commands.BadArgument("Choose a text channel in this server.")
        if not can_send(channel):
            raise commands.BadArgument("The bot needs View Channel, Send Messages and Embed Links there.")
        self.store.set(inter.guild.id, channel.id)
        await inter.response.send_message(f"Announcements will be sent to {channel.mention}.", ephemeral=True)

    @commands.slash_command(description="Stop announcements for this server (server owner only).")
    @commands.guild_only()
    @commands.check(require_guild_owner)
    async def unpublish(self, inter: disnake.ApplicationCommandInteraction):
        self.store.remove(inter.guild.id)
        await inter.response.send_message("Announcements disabled for this server.", ephemeral=True)

    @commands.slash_command(description="Send an announcement to subscribed servers (bot owner only).")
    @commands.guild_only()
    @commands.is_owner()
    @commands.max_concurrency(1, per=commands.BucketType.default, wait=False)
    async def broadcast(
        self,
        inter: disnake.ApplicationCommandInteraction,
        message: str = commands.Param(min_length=1, max_length=4096),
        title: str = commands.Param(min_length=1, max_length=256),
        thumbnail_url: str = commands.Param(default=None, max_length=2048),
        thumbnail: disnake.Attachment = None,
    ):
        if not message.strip() or not title.strip():
            raise commands.BadArgument("Message and title cannot be blank.")
        await inter.response.defer(ephemeral=True)
        image = await prepare_thumbnail(thumbnail_url, thumbnail)
        embed = disnake.Embed(title=title, description=message)
        if image.url:
            embed.set_thumbnail(url=image.url)
        sent = 0
        skipped = 0
        for guild in list(inter.bot.guilds):
            channel = broadcast_channel(guild, self.store, needs_attachment=image.data is not None)
            if channel is None or (image.data is not None and len(image.data) > guild.filesize_limit):
                skipped += 1
                continue
            with image.open_file() as file:
                if await send_broadcast(channel, embed, file=file):
                    sent += 1
                else:
                    skipped += 1
        await inter.edit_original_response(
            content=f"Broadcast sent to {sent} server(s). Skipped or failed: {skipped}."
        )
