import asyncio
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import disnake
from aiohttp import ClientConnectionError, FormData, web
from aiohttp.test_utils import TestClient, TestServer

from api_server import MAX_REQUEST, MAX_UPLOAD, create_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.channel = Mock(spec=disnake.TextChannel)
        self.channel.id = 123
        self.channel.name = "general"
        self.channel.guild = SimpleNamespace(me=object(), filesize_limit=100, owner_id=42)
        self.channel.permissions_for.return_value = SimpleNamespace(
            view_channel=True, send_messages=True, attach_files=True)
        self.channel.send = AsyncMock(return_value=SimpleNamespace(id=456, jump_url="test"))
        self.bot = Mock()
        self.bot.is_ready.return_value = True
        self.bot.get_channel.return_value = self.channel
        self.bot.guilds = []
        self.resolve_user_id = AsyncMock(return_value=42)
        self.http = TestClient(TestServer(create_app(self.bot, resolve_user_id=self.resolve_user_id)))
        await self.http.start_server()

    async def asyncTearDown(self):
        await self.http.close()

    async def test_authenticated_routes_and_public_health(self):
        self.assertEqual((await self.http.get("/health")).status, 200)
        self.assertEqual((await self.http.get("/channels")).status, 200)

    async def test_text(self):
        response = await self.http.post('/publish', json={"channel_id": "123", "message": "Hello"})
        self.assertEqual(response.status, 201)
        self.assertEqual((await response.json())["message_id"], "456")
        self.channel.send.assert_awaited_once()

    async def test_invalid_requests(self):
        for payload in ({}, [], {"channel_id": "123"},
                        {"channel_id": "123", "message": "x" * 2001}):
            response = await self.http.post('/publish', json=payload)
            self.assertEqual(response.status, 400)
        self.channel.send.assert_not_awaited()

    async def test_not_ready(self):
        self.bot.is_ready.return_value = False
        response = await self.http.post('/publish', json={})
        self.assertEqual(response.status, 503)

    async def test_upload(self):
        form = FormData()
        form.add_field('channel_id', '123')
        form.add_field('media', b'example', filename='hello.txt')
        response = await self.http.post('/publish', data=form)
        self.assertEqual(response.status, 201)
        self.assertEqual(self.channel.send.await_args.kwargs["file"].filename, "hello.txt")

    async def test_mounted_app_accepts_upload_above_one_mib(self):
        payload = b'x' * (2 * 1024 * 1024)
        self.channel.guild.filesize_limit = MAX_UPLOAD
        async def capture(**kwargs):
            self.assertEqual(kwargs["file"].fp.read(), payload)
            return SimpleNamespace(id=456, jump_url="test")
        self.channel.send.side_effect = capture
        parent = web.Application(client_max_size=MAX_REQUEST)
        parent.add_subapp('/discord/', create_app(self.bot, resolve_user_id=self.resolve_user_id))
        async with TestClient(TestServer(parent)) as client:
            form = FormData()
            form.add_field('channel_id', '123')
            form.add_field('media', io.BytesIO(payload), filename='clip.mp4')
            response = await client.post('/discord/publish', data=form)
            self.assertEqual(response.status, 201)
            self.assertEqual((await response.json())["message_id"], "456")
        self.channel.send.assert_awaited_once()

    async def test_server_upload_limit(self):
        form = FormData()
        form.add_field('channel_id', '123')
        form.add_field('media', b'x' * 101, filename='test.txt')
        response = await self.http.post('/publish', data=form)
        self.assertEqual(response.status, 413)
        self.channel.send.assert_not_awaited()

    async def test_image_and_video_keep_caption_and_original_bytes(self):
        for filename, payload in [('image.png', b'image-data'), ('clip.mp4', b'video-data')]:
            async def capture(**kwargs):
                self.assertEqual(kwargs['content'], 'Prepared caption')
                self.assertEqual(kwargs['file'].fp.read(), payload)
                self.assertEqual(kwargs['file'].filename, filename)
                self.assertFalse(kwargs['allowed_mentions'].everyone)
                return SimpleNamespace(id=456, jump_url='test')
            self.channel.send.side_effect = capture
            form = FormData()
            form.add_field('channel_id', '123')
            form.add_field('message', 'Prepared caption')
            form.add_field('media', payload, filename=filename)
            response = await self.http.post('/publish', data=form)
            self.assertEqual(response.status, 201)
            self.assertEqual((await response.json())['delivery_status'], 'delivered')

    async def test_duplicate_fields_do_not_publish(self):
        for field in ('channel_id', 'media'):
            form = FormData()
            form.add_field('channel_id', '123')
            form.add_field('media', b'image', filename='image.png')
            if field == 'media':
                form.add_field('media', b'video', filename='video.mp4')
            else:
                form.add_field('channel_id', '999')
            self.assertEqual((await self.http.post('/publish', data=form)).status, 400)
        self.channel.send.assert_not_awaited()

    async def test_exact_upload_limit_with_caption_on_parent_app(self):
        self.channel.guild.filesize_limit = MAX_REQUEST
        parent = web.Application(client_max_size=MAX_REQUEST)
        parent.add_subapp('/discord/', create_app(self.bot, resolve_user_id=self.resolve_user_id))
        async with TestClient(TestServer(parent)) as client:
            for size, expected in ((MAX_UPLOAD, 201), (MAX_UPLOAD + 1, 413)):
                form = FormData()
                form.add_field('channel_id', '123')
                form.add_field('message', 'c' * 2000)
                form.add_field('media', io.BytesIO(b'x' * size), filename='clip.mp4')
                self.assertEqual((await client.post('/discord/publish', data=form)).status, expected)
        self.channel.send.assert_awaited_once()

    async def test_permissions(self):
        self.channel.send.side_effect = disnake.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "denied")
        response = await self.http.post('/publish', json={"channel_id": "123", "message": "Hello"})
        self.assertEqual(response.status, 403)

    async def test_uncertain_send_is_not_retryable(self):
        failures = [asyncio.TimeoutError(), ClientConnectionError('lost response'),
                    disnake.HTTPException(SimpleNamespace(status=500, reason='Server error'), 'error')]
        for failure in failures:
            self.channel.send.reset_mock()
            self.channel.send.side_effect = failure
            response = await self.http.post('/publish', json={'channel_id': '123', 'message': 'Hello'})
            self.assertEqual(response.status, 502)
            body = await response.json()
            self.assertEqual(body['delivery_status'], 'unknown')
            self.assertIs(body['retryable'], False)
            self.channel.send.assert_awaited_once()

    async def test_uncertain_upload_is_not_retryable(self):
        self.channel.send.side_effect = asyncio.TimeoutError()
        form = FormData()
        form.add_field('channel_id', '123')
        form.add_field('media', b'image', filename='image.png')
        response = await self.http.post('/publish', data=form)
        self.assertEqual((await response.json())['delivery_status'], 'unknown')
        self.channel.send.assert_awaited_once()

    async def test_missing_resolver_fails_closed_even_with_spoofed_identity(self):
        async with TestClient(TestServer(create_app(self.bot))) as client:
            headers = {'X-Discord-User-ID': '42'}
            self.assertEqual((await client.get('/health')).status, 200)
            self.assertEqual((await client.get('/channels?user_id=42', headers=headers)).status, 401)
            response = await client.post('/publish', headers=headers, json={
                'channel_id': '123', 'message': 'Hello', 'user_id': '42'})
            self.assertEqual(response.status, 401)
        self.channel.send.assert_not_awaited()

    async def test_missing_or_invalid_session_identity(self):
        for identity in (None, '', True, 'invalid', 0):
            self.resolve_user_id.return_value = identity
            self.assertEqual((await self.http.get('/channels')).status, 401)
            self.assertEqual((await self.http.post('/publish', json={})).status, 401)
        self.channel.send.assert_not_awaited()

    async def test_channel_listing_is_owner_scoped(self):
        own = SimpleNamespace(id=1, name='Own', owner_id=42, me=object(), text_channels=[self.channel])
        other = SimpleNamespace(id=2, name='Other', owner_id=99, me=object(), text_channels=[self.channel])
        self.bot.guilds = [own, other]
        response = await self.http.get('/channels?user_id=99', headers={'X-Discord-User-ID': '99'})
        self.assertEqual([g['id'] for g in (await response.json())['servers']], ['1'])
        self.resolve_user_id.return_value = 77
        self.assertEqual((await (await self.http.get('/channels')).json())['servers'], [])

    async def test_other_owner_and_transferred_server_cannot_publish(self):
        # The destination was previously owned by this user; ownership is checked again.
        self.channel.guild.owner_id = 99
        response = await self.http.post('/publish', json={
            'channel_id': '123', 'message': 'Hello', 'user_id': '99'})
        self.assertEqual(response.status, 404)
        form = FormData()
        form.add_field('channel_id', '123')
        form.add_field('media', b'image', filename='test.png')
        self.assertEqual((await self.http.post('/publish', data=form)).status, 404)
        self.channel.send.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
