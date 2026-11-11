"""Persistent, explicit guild opt-in for announcements."""

import sqlite3
from contextlib import closing


class ChannelStore:
    def __init__(self, path):
        self.path = str(path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS channels (guild_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL)")

    def get(self, guild_id):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT channel_id FROM channels WHERE guild_id = ?", (str(guild_id),)).fetchone()
        return int(row[0]) if row else None

    def set(self, guild_id, channel_id):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (str(guild_id), str(channel_id)))

    def remove(self, guild_id):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM channels WHERE guild_id = ?", (str(guild_id),))
