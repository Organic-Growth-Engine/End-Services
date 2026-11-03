# Telegram Publishing Bot

## Files

| File                 | Purpose                                          |
| -------------------- | ------------------------------------------------ |
| `config.py`          | Loads `.env` and exposes `BOT_TOKEN` & `CHAT_ID` |
| `telegram_client.py` | Small async Telegram Bot API client              |
| `publisher.py`       | Validate and publish text, media or albums       |
| `worker.py`          | Publish a post supplied by the caller            |
| `main.py`            | Runs the worker with a sample post and chat      |

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Add the bot to the channel as an **administrator** and enable **Post messages**.
3. Configure the environment:

   ```bash
   cp .env.example .env
   # set BOT_TOKEN & CHAT_ID
   uv sync
   ```

## Usage

```bash
# Publish the sample post
uv run main.py
```

## Post format

```python
{
    "id": 1,  # optional, used in logs
    "content": "Post text",  # optional when media is present
    "parse_mode": "HTML",  # optional
    "media": [  # optional
        {
            "type": "photo",  # photo, video, document, audio, animation
            "url": "https://example.com/a.jpg",  # required
            "caption": "Optional caption",  # optional, max 1024 characters
            "parse_mode": "HTML",  # optional
        }
    ],
}
```
