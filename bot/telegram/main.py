"""Telegram bot that broadcasts posts to every configured channel."""

import json
import logging

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, CHAT_IDS, OWNER_USER_ID
from worker import broadcast_post

logger = logging.getLogger(__name__)

HELP_TEXT = """<b>Broadcast Bot</b>

<b>Publish a post</b>
<code>/broadcast &lt;text&gt;</code>
<code>/broadcast &lt;json&gt;</code>
Reply to any message with <code>/broadcast</code> to publish it.
Or send the payload to me, then send <code>/broadcast</code>.

<b>Commands</b>
• <code>/channels</code> — list configured channels
• <code>/id</code> — show your user id
• <code>/help</code> — show this message

<b>JSON payload example</b>
<pre>{"content": "Post text", "media": [{"type": "photo", "url": "https://example.com/a.jpg"}]}</pre>"""

MEDIA_KEYS = ("photo", "video", "document", "audio", "animation")


def _parse_command(text: str) -> tuple[str | None, str]:
    """Return (command, arguments) for messages such as ``/post@MyBot hello``."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None, ""

    parts = text.split(maxsplit=1)
    command = parts[0][1:].split("@", 1)[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return command or None, args


def _post_from_message(message: Message) -> dict:
    """Convert a Telegram message into a post payload."""
    post: dict = {}

    content = (message.text or message.caption or "").strip()
    if content:
        post["content"] = content

    media = []
    for media_type in MEDIA_KEYS:
        value = getattr(message, media_type, None)
        if not value:
            continue
        if media_type == "photo":
            file_id = value[-1].file_id
        else:
            file_id = value.file_id
        if file_id:
            media.append({"type": media_type, "url": file_id})

    if media:
        post["media"] = media
    return post


def _post_from_args(args: str) -> dict:
    """Build a post from the command arguments (plain text or a JSON object)."""
    if args.lstrip().startswith("{"):
        try:
            post = json.loads(args)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON payload: {exc.msg}.") from exc
        if not isinstance(post, dict):
            raise ValueError("The JSON payload must be an object.")
        return post
    return {"content": args}


def _format_results(results: dict) -> str:
    total = len(results)
    published = sum(1 for result in results.values() if result is not None)
    lines = [f"Broadcast finished: {published}/{total} channels."]
    for chat, result in results.items():
        lines.append(f"{'OK' if result is not None else 'FAILED'} - {chat}")
    return "\n".join(lines)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    channels = "\n".join(f"- {chat}" for chat in CHAT_IDS) or "- none"
    await update.effective_message.reply_text(
        f"Configured channels ({len(CHAT_IDS)}):\n{channels}"
    )


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        f"User id: {update.effective_user.id}\nChat id: {update.effective_chat.id}"
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    _, args = _parse_command(message.text or "")

    try:
        if args:
            post = _post_from_args(args)
        elif message.reply_to_message:
            post = _post_from_message(message.reply_to_message)
        elif context.chat_data.get("pending_post"):
            post = context.chat_data["pending_post"]
        else:
            await message.reply_text(
                "Usage: /broadcast <text|json>, reply to a message with "
                "/broadcast, or send a payload first and then /broadcast."
            )
            return
    except ValueError as exc:
        await message.reply_text(str(exc))
        return

    if not post.get("content") and not post.get("media"):
        await message.reply_text("The broadcast payload has no content or media.")
        return

    logger.info(
        "Broadcasting post from user %s to %s.", update.effective_user.id, CHAT_IDS
    )
    results = await broadcast_post(post, CHAT_IDS, bot=context.bot)
    if all(result is not None for result in results.values()):
        context.chat_data.pop("pending_post", None)
    await message.reply_text(_format_results(results))


async def save_payload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    post = _post_from_message(message)
    if not post.get("content") and not post.get("media"):
        return

    context.chat_data["pending_post"] = post
    await message.reply_text("Payload saved. Send /broadcast to publish it.")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    missing = [
        name
        for name, value in (
            ("BOT_TOKEN", BOT_TOKEN),
            ("CHAT_IDS", CHAT_IDS),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    allowed_chat = filters.ChatType.PRIVATE
    if OWNER_USER_ID is None:
        logger.warning(
            "OWNER_USER_ID is not set; any private chat can issue broadcast commands."
        )
    else:
        allowed_chat &= filters.User(user_id=OWNER_USER_ID)

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler(
            ["start", "help"], help_command, filters=filters.ChatType.PRIVATE
        )
    )
    application.add_handler(
        CommandHandler("id", id_command, filters=filters.ChatType.PRIVATE)
    )
    application.add_handler(
        CommandHandler("channels", channels_command, filters=allowed_chat)
    )
    application.add_handler(
        CommandHandler(
            ["broadcast", "post", "send"], broadcast_command, filters=allowed_chat
        )
    )
    application.add_handler(
        MessageHandler(allowed_chat & ~filters.COMMAND, save_payload)
    )

    application.run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
