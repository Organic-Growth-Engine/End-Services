import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import disnake
from aiohttp import ClientConnectionError
from disnake.ext import commands

from channel_store import ChannelStore
from publisher import Publisher, broadcast_channel, prepare_thumbnail, require_guild_owner


def make_guild(guild_id, channel_id):
    guild = Mock(id=guild_id, owner_id=42, filesize_limit=100)
    channel = Mock(spec=disnake.TextChannel)
    channel.id = channel_id
    channel.guild = guild
    channel.mention = f'<#{channel_id}>'
    channel.permissions_for.return_value = SimpleNamespace(
        view_channel=True, send_messages=True, embed_links=True, attach_files=True)
    channel.send = AsyncMock()
    guild.get_channel.side_effect = lambda selected: channel if selected == channel_id else None
    return guild, channel


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'channels.sqlite3'
        self.store = ChannelStore(self.path)
        self.publisher = Publisher(self.store)
        self.guild, self.channel = make_guild(1, 10)
        self.inter = SimpleNamespace(
            guild=self.guild, author=SimpleNamespace(id=42),
            response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
            edit_original_response=AsyncMock(), bot=SimpleNamespace(guilds=[self.guild]))

    async def test_selection_persists_replaces_and_unsubscribes(self):
        await Publisher.publish.callback(self.publisher, self.inter, self.channel)
        self.assertEqual(ChannelStore(self.path).get(1), 10)
        self.store.set(1, 11)
        self.assertEqual(ChannelStore(self.path).get(1), 11)
        await Publisher.unpublish.callback(self.publisher, self.inter)
        self.assertIsNone(ChannelStore(self.path).get(1))
        self.inter.response.send_message.assert_awaited()
        self.assertTrue(self.inter.response.send_message.await_args.kwargs['ephemeral'])

    async def test_ownership_checks(self):
        for command in (Publisher.publish, Publisher.unpublish):
            self.assertIn(require_guild_owner, command.checks)
        self.assertTrue(require_guild_owner(self.inter))
        self.inter.author.id = 99
        with self.assertRaises(commands.CheckFailure):
            require_guild_owner(self.inter)
        self.inter.guild = None
        with self.assertRaises(commands.NoPrivateMessage):
            require_guild_owner(self.inter)
        self.inter.bot.is_owner = AsyncMock(return_value=False)
        # Checks are not guaranteed to retain decorator order.
        self.inter.guild_id = 1
        async def owner_check(inter):
            for check in Publisher.broadcast.checks:
                result = check(inter)
                if asyncio.iscoroutine(result):
                    await result
            return True
        with self.assertRaises(commands.NotOwner):
            await owner_check(self.inter)
        self.inter.bot.is_owner.return_value = True
        self.assertTrue(await owner_check(self.inter))

    async def test_configuration_rejects_other_guild_or_missing_permissions(self):
        _, other = make_guild(2, 20)
        for channel in (other, self.channel):
            self.channel.permissions_for.return_value.embed_links = False
            with self.assertRaises(commands.BadArgument):
                await Publisher.publish.callback(self.publisher, self.inter, channel)
        self.assertIsNone(self.store.get(1))

    async def test_no_automatic_channel_fallback(self):
        self.assertIsNone(broadcast_channel(self.guild, self.store))
        self.store.set(1, 999)
        self.assertIsNone(broadcast_channel(self.guild, self.store))
        self.store.set(1, 10)
        self.assertIs(broadcast_channel(self.guild, self.store), self.channel)
        for permission in ('view_channel', 'send_messages', 'embed_links', 'attach_files'):
            with self.subTest(permission=permission):
                setattr(self.channel.permissions_for.return_value, permission, False)
                self.assertIsNone(broadcast_channel(self.guild, self.store, needs_attachment=True))
                setattr(self.channel.permissions_for.return_value, permission, True)

    async def test_thumbnail_modes_and_validation(self):
        image = await prepare_thumbnail()
        with image.open_file() as file:
            self.assertIsNone(file)
        self.assertEqual((await prepare_thumbnail('https://example.com/a.png')).url,
                         'https://example.com/a.png')
        attachment = SimpleNamespace(filename='a.PNG', size=3, read=AsyncMock(return_value=b'abc'))
        image = await prepare_thumbnail(attachment=attachment)
        self.assertEqual(image.url, 'attachment://thumbnail.png')
        with image.open_file() as file:
            self.assertEqual(file.fp.read(), b'abc')
        self.assertTrue(file.fp.closed)
        for url, upload in [('file:///a', None), ('https://example.com/a', attachment),
                            (None, SimpleNamespace(filename='a.exe', size=1)),
                            (None, SimpleNamespace(filename='a.png', size=26*1024*1024))]:
            with self.subTest(url=url, upload=upload), self.assertRaises(commands.BadArgument):
                await prepare_thumbnail(url, upload)

    async def test_broadcast_only_selected_channels_and_continues_after_failure(self):
        guild2, channel2 = make_guild(2, 20)
        guild3, channel3 = make_guild(3, 30)
        self.inter.bot.guilds.extend([guild2, guild3])
        self.store.set(1, 10)
        self.store.set(3, 30)
        self.channel.send.side_effect = disnake.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'denied')
        streams = []
        async def capture(**kwargs):
            streams.append(kwargs['file'].fp)
            self.assertEqual(kwargs['file'].fp.read(), b'abc')
            self.assertFalse(kwargs['allowed_mentions'].everyone)
        channel3.send.side_effect = capture
        attachment = SimpleNamespace(filename='a.png', size=3, read=AsyncMock(return_value=b'abc'))
        await Publisher.broadcast.callback(self.publisher, self.inter, 'Hello', 'Title', None, attachment)
        self.channel.send.assert_awaited_once()
        channel2.send.assert_not_awaited()
        channel3.send.assert_awaited_once()
        self.assertTrue(streams[0].closed)
        self.assertTrue(self.channel.send.await_args.kwargs['file'].fp.closed)
        self.inter.edit_original_response.assert_awaited_once_with(
            content='Broadcast sent to 1 server(s). Skipped or failed: 2.')

    async def test_network_failure_does_not_stop_later_servers(self):
        guild2, channel2 = make_guild(2, 20)
        self.inter.bot.guilds.append(guild2)
        self.store.set(1, 10)
        self.store.set(2, 20)
        for error in (ClientConnectionError("lost connection"), asyncio.TimeoutError()):
            with self.subTest(error=type(error).__name__):
                self.channel.send.side_effect = error
                channel2.send.reset_mock()
                await Publisher.broadcast.callback(self.publisher, self.inter, 'Hello', 'Title', None, None)
                channel2.send.assert_awaited_once()
                self.inter.edit_original_response.assert_awaited_with(
                    content='Broadcast sent to 1 server(s). Skipped or failed: 1.')

    async def test_upload_limit_and_text_broadcast(self):
        self.store.set(1, 10)
        attachment = SimpleNamespace(filename='a.png', size=101, read=AsyncMock(return_value=b'x'*101))
        await Publisher.broadcast.callback(self.publisher, self.inter, 'Hello', 'Title', None, attachment)
        self.channel.send.assert_not_awaited()
        await Publisher.broadcast.callback(self.publisher, self.inter, 'Hello', 'Title', None, None)
        self.channel.send.assert_awaited_once()
        self.assertIsNone(self.channel.send.await_args.kwargs['file'])

    async def test_unsubscribed_and_blank_broadcasts_do_not_send(self):
        await Publisher.broadcast.callback(self.publisher, self.inter, 'Hello', 'Title', None, None)
        self.channel.send.assert_not_awaited()
        self.inter.edit_original_response.assert_awaited_once_with(
            content='Broadcast sent to 0 server(s). Skipped or failed: 1.')
        for message, title in [(' ', 'Title'), ('Hello', ' ')]:
            with self.assertRaises(commands.BadArgument):
                await Publisher.broadcast.callback(self.publisher, self.inter, message, title, None, None)
        self.channel.send.assert_not_awaited()

    async def test_url_thumbnail_delivery(self):
        self.store.set(1, 10)
        await Publisher.broadcast.callback(self.publisher, self.inter, 'Hello', 'Title',
                                           'https://example.com/image.png', None)
        kwargs = self.channel.send.await_args.kwargs
        self.assertEqual(kwargs['embed'].thumbnail.url, 'https://example.com/image.png')
        self.assertIsNone(kwargs['file'])

    async def test_commands_register(self):
        bot = commands.InteractionBot()
        try:
            bot.add_cog(self.publisher)
            self.assertEqual({command.name for command in bot.slash_commands},
                             {'publish', 'unpublish', 'broadcast'})
        finally:
            await bot.close()


if __name__ == '__main__':
    unittest.main()
