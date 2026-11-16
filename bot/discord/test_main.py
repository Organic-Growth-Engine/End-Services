import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from main import create_bot


class FactorySyncTests(unittest.TestCase):
    def test_rejects_sync_construction_before_creating_client_or_store(self):
        with patch('main.commands.InteractionBot') as client:
            with self.assertRaisesRegex(RuntimeError, 'async startup'):
                create_bot()
            client.assert_not_called()


class FactoryAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_uses_parent_loop_and_prepares_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = create_bot()
            try:
                self.assertIs(bot.loop, asyncio.get_running_loop())
                self.assertEqual({c.name for c in bot.slash_commands},
                                 {'publish'})
                prepared = asyncio.Event()
                bot._cache_application_commands = AsyncMock()
                bot._sync_application_commands = AsyncMock(side_effect=lambda: prepared.set())
                bot._fill_owners = AsyncMock()
                bot._first_connect.set()
                # Exercise real command preparation while preventing any network login.
                with patch('disnake.Client.login', new=AsyncMock()):
                    await bot.login('test-only-token')
                await asyncio.wait_for(prepared.wait(), timeout=1)
                bot._sync_application_commands.assert_awaited_once()
            finally:
                await bot.close()


if __name__ == '__main__':
    unittest.main()
