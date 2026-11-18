import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import disnake
from disnake.ext import commands
from publisher import Publisher, MAX_UPLOAD


def guild(owner, ids):
    g = SimpleNamespace(owner_id=owner, me=object(), filesize_limit=MAX_UPLOAD)
    g.text_channels = []
    for cid in ids:
        c = Mock(spec=disnake.TextChannel)
        c.id = cid
        c.permissions_for.return_value = SimpleNamespace(
            view_channel=True, send_messages=True, attach_files=True)
        c.send = AsyncMock()
        g.text_channels.append(c)
    return g


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.own = guild(42, [1, 2])
        self.other = guild(99, [3])
        self.inter = SimpleNamespace(
            author=SimpleNamespace(id=42), bot=SimpleNamespace(guilds=[self.own, self.other]),
            response=SimpleNamespace(defer=AsyncMock()), edit_original_response=AsyncMock(),
            followup=SimpleNamespace(send=AsyncMock()))
        self.publisher = Publisher()

    async def publish(self, message='Caption', media=None):
        await Publisher.publish.callback(self.publisher, self.inter, message, media)

    async def test_all_channels_in_all_owned_servers_only(self):
        another = guild(42, [4])
        self.inter.bot.guilds.append(another)
        await self.publish()
        for c in self.own.text_channels + another.text_channels:
            c.send.assert_awaited_once()
        self.other.text_channels[0].send.assert_not_awaited()
        self.assertIn('3 channel(s)', self.inter.edit_original_response.await_args.kwargs['content'])

    async def test_media_read_once_and_fresh_closed_stream_per_channel(self):
        streams = []
        async def capture(**kwargs):
            streams.append(kwargs['file'].fp)
            self.assertEqual(kwargs['file'].fp.read(), b'video')
            self.assertEqual(kwargs['content'], 'Caption')
            self.assertFalse(kwargs['allowed_mentions'].everyone)
        for c in self.own.text_channels:
            c.send.side_effect = capture
        media = SimpleNamespace(size=5, filename='clip.mp4', read=AsyncMock(return_value=b'video'))
        await self.publish(media=media)
        media.read.assert_awaited_once()
        self.assertEqual(len(streams), 2)
        self.assertIsNot(streams[0], streams[1])
        self.assertTrue(all(s.closed for s in streams))

    async def test_no_owned_servers_or_empty_payload(self):
        with self.assertRaises(commands.BadArgument):
            await self.publish(message=' ')
        self.inter.author.id = 77
        with self.assertRaises(commands.CheckFailure):
            await self.publish()
        for c in self.own.text_channels:
            c.send.assert_not_awaited()

    async def test_permission_and_size_limits_skip_channels(self):
        self.own.text_channels[0].permissions_for.return_value.attach_files = False
        self.own.filesize_limit = 4
        media = SimpleNamespace(size=5, filename='a.png', read=AsyncMock(return_value=b'image'))
        await self.publish(media=media)
        for c in self.own.text_channels:
            c.send.assert_not_awaited()
        media.size = MAX_UPLOAD + 1
        with self.assertRaises(commands.BadArgument):
            await self.publish(media=media)

    async def test_failed_send_continues_and_confirmation_failure_does_not_resend(self):
        failure = disnake.HTTPException(SimpleNamespace(status=500, reason='error'), 'error')
        self.own.text_channels[0].send.side_effect = failure
        self.inter.edit_original_response.side_effect = failure
        self.inter.followup.send.side_effect = failure
        await self.publish()
        for c in self.own.text_channels:
            c.send.assert_awaited_once()

    async def test_ownership_change_before_later_channel_blocks_send(self):
        async def transfer(**kwargs):
            self.own.owner_id = 99
        self.own.text_channels[0].send.side_effect = transfer
        await self.publish()
        self.own.text_channels[1].send.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
