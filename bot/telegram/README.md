# Telegram Publishing Bot

A long-running bot that accepts broadcast commands in a private chat and
publishes each post to every configured Telegram channel. It uses
[`python-telegram-bot`](https://python-telegram-bot.org/) for polling, commands
and Telegram API calls.

## Files

| File           | Purpose                                                           |
| -------------- | ----------------------------------------------------------------- |
| `config.py`    | Loads `.env` and exposes `BOT_TOKEN`, `OWNER_USER_ID`, `CHAT_IDS` |
| `publisher.py` | Validate and publish text, media or albums                        |
| `worker.py`    | Publish a post to one chat or broadcast it to many chats          |
| `main.py`      | Registers bot commands and fans out the payload                   |

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Add the bot as an **administrator** to every destination channel and enable
   **Post messages**.
3. Configure the environment:

   ```bash
   cp .env.example .env
   # set BOT_TOKEN and CHAT_IDS
   uv sync
   ```

4. Optionally set `OWNER_USER_ID` to restrict command access to your account.
   Start the bot and send `/id` to see your user id.

### Environment

| Variable        | Required | Description                                                               |
| --------------- | -------- | ------------------------------------------------------------------------- |
| `BOT_TOKEN`     | yes      | Bot token from @BotFather                                                 |
| `CHAT_IDS`      | yes      | Destination chats as a JSON array                                         |
| `OWNER_USER_ID` | no       | Only this Telegram user may run broadcasts; empty allows any private chat |

`CHAT_IDS` must be a JSON array. It accepts both integer ids and `@username`
values:

```bash
CHAT_IDS=["-1001111111111", "-1002222222222", "@my_channel"]
```

## Usage

Run the bot:

```bash
uv run main.py
```

Then send commands to the bot in a private chat:

| Command                   | Description                                             |
| ------------------------- | ------------------------------------------------------- |
| `/broadcast <text>`       | Broadcast plain text to every configured chat           |
| `/broadcast <json>`       | Broadcast a structured post payload (text + media URLs) |
| `/broadcast` (as a reply) | Broadcast the message you replied to (text or media)    |
| `/broadcast`              | Broadcast the last payload sent to the bot              |
| `/channels`               | List the configured destination chats                   |
| `/id`                     | Show your user id and the current chat id               |
| `/help`                   | Show command help                                       |

The bot only reacts in private chats. If `OWNER_USER_ID` is set, commands from
other users are ignored.

## Post format

The JSON form of `/broadcast` uses the same payload as `worker.broadcast_post`:

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

Example:

```text
/broadcast {"content": "New post", "media": [{"type": "photo", "url": "https://picsum.photos/1200/800"}]}
```

Replying with `/broadcast` to a text or media message reuses that message's
content (media is referenced by its Telegram `file_id`). Media groups/albums
should use the JSON payload instead.
