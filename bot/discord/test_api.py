import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import disnake
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from api_server import create_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.channel = Mock(spec=disnake.TextChannel)
        self.channel.id = 123
        self.channel.name = "general"
        self.channel.guild = SimpleNamespace(me=object(), filesize_limit=100)
        self.channel.permissions_for.return_value = SimpleNamespace(
            view_channel=True, send_messages=True, attach_files=True)
        self.channel.send = AsyncMock(return_value=SimpleNamespace(id=456, jump_url="test"))
        self.bot = Mock()
        self.bot.is_ready.return_value = True
        self.bot.get_channel.return_value = self.channel
        self.bot.guilds = []
        self.http = TestClient(TestServer(create_app(self.bot)))
        await self.http.start_server()

    async def asyncTearDown(self):
        await self.http.close()

    async def test_internal_routes_need_no_separate_key(self):
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

    async def test_server_upload_limit(self):
        form = FormData()
        form.add_field('channel_id', '123')
        form.add_field('media', b'x' * 101, filename='test.txt')
        response = await self.http.post('/publish', data=form)
        self.assertEqual(response.status, 413)
        self.channel.send.assert_not_awaited()

    async def test_permissions(self):
        self.channel.send.side_effect = disnake.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "denied")
        response = await self.http.post('/publish', json={"channel_id": "123", "message": "Hello"})
        self.assertEqual(response.status, 403)


if __name__ == '__main__':
    unittest.main()
