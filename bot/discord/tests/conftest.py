import os

# Set before config.py is imported; load_dotenv doesn't override these.
os.environ["DISCORD_BOT_TOKEN"] = "test-token"
os.environ["DISCORD_CHANNEL_IDS"] = '["111", "222"]'
