# Discord publishing integration

A small adapter for the parent dashboard: list eligible channels and send a
prepared image/video and caption to a selected text channel. No caption generation,
conversion, analytics, scheduling, or queues. Discord slash commands are also
supported through a single `/publish` command. No subscription database is needed.

Requires Python 3.10+ and the packages in `requirements.txt`. Invite the bot with
the `bot` and `applications.commands` scopes, and View Channel, Send Messages,
Attach Files and Embed Links permissions. No privileged intents are needed.

## Parent integration

The parent owns login, verified Discord account linking, secrets, and the web
listener. Pass an async `resolve_user_id(request)` that returns the logged-in
user's verified Discord ID from the parent's session. Do not take it directly
from a request header, URL, or form field. The small owner check stays here so
channel discovery and publishing consistently enforce the owner-only rule.
No resolver or no identity means HTTP 401. Other owners' channels are omitted
from listings and return the same HTTP 404 as unknown channels when publishing.
Ownership is checked against the bot's current gateway cache on every request.

Create the client inside the running parent event loop. With this project directory on the Python import path:

```python
import asyncio
from contextlib import suppress
from aiohttp import web
from main import create_bot
from api_server import MAX_REQUEST, create_app

async def build_app(token, resolve_user_id, auth_middleware):
    bot = create_bot()
    app = web.Application(
        middlewares=[auth_middleware], client_max_size=MAX_REQUEST)
    app.add_subapp('/discord/', create_app(bot, resolve_user_id=resolve_user_id))

    async def discord_lifecycle(app):
        task = asyncio.create_task(bot.start(token))
        try:
            yield
        finally:
            task.cancel()
            try:
                with suppress(asyncio.CancelledError):
                    await task
            finally:
                await bot.close()

    app.cleanup_ctx.append(discord_lifecycle)
    return app
```

The parent awaits this app factory on the same loop used to serve the app and
supplies its real authentication middleware and session resolver. Keep these
routes behind that backend. The parent handles service supervision and should
observe connection readiness and unexpected bot-task failures. `/health` reports
`{"ready": false}` while Discord is disconnected; publishing returns HTTP 503.
Importing this module reads no `.env`, opens no database, and starts no listener.
There is no standalone command; the parent owns startup/shutdown.

## API

| Route | Input | Result |
| --- | --- | --- |
| `GET /discord/health` | None | Discord connection readiness (HTTP 200; inspect `ready`) |
| `GET /discord/channels` | Authenticated parent session | Owned servers and channels the bot can view and send to; IDs are strings |
| `POST /discord/publish` | Multipart `channel_id`, optional `message`, one `media` file | HTTP 201 with message ID, channel ID, URL and `delivery_status: "delivered"` |

`message` is the prepared caption, at most 2000 characters. Text-only publishing
also accepts JSON with `channel_id` and `message`. Supply text, media, or both.
Mentions do not ping users/roles. The file is forwarded unchanged; the parent
prepares suitable formats, aspect ratios, and captions. No server file paths or
URL downloads are accepted. Repeated multipart fields are rejected.

Files may be up to the smaller of **24 MiB** and the destination server's limit.
The full request budget is **25 MiB**, leaving room for framing and captions.
Configure the parent with `MAX_REQUEST`; its default 1 MiB limit otherwise wins.
Discord can still reject content or uploads; those errors are returned to the caller.

For several selected destinations, the parent makes one publish request per
channel and tracks each result. This deliberately avoids a second batch/job
system inside the integration. `/channels` is channel discovery, not a saved
connection list; the parent stores the user's selections and any delivery records.

## Failed or uncertain delivery

A send timeout, connection failure, or Discord server error returns HTTP 502 with
`delivery_status: "unknown"`, `retryable: false`, and advice to check Discord
before retrying. Treat a lost HTTP response as unknown too. The parent must not
blindly retry publish POSTs. No extra retry loop is added here, but Disnake may
retry internally; this adapter does not guarantee duplicate-free delivery.

## Discord slash command

`/publish [message] [media]` sends the caption and/or uploaded image/video to
**every eligible text channel in every server owned by the invoking user where
the bot is installed**. This includes private text channels the bot can access.
It is not limited to the channel/server where the command is invoked.

Only server ownership qualifies; administrator permissions or bot-application
ownership do not grant access to another owner's servers. The command must be
invoked in a server. It needs a caption, a file, or both; captions have a 2000
character limit and files a 24 MiB limit. Individual destination upload limits
and View Channel, Send Messages, and Attach Files permissions are respected.
Text-only sends do not require Attach Files or Embed Links.

There is no channel selection, opt-in subscription, `/broadcast`, or `/unpublish`
command. Only `/publish` is registered. The library syncs the new command set on
connection; Discord may take time to show the changes. Existing SQLite files
are left untouched but unused; `create_bot()` no longer accepts `store_path`.

Each invocation targets each eligible text channel once, continues after a send
failure, suppresses mentions, and reports a private summary. One publish runs
per user at a time. Library retries can still cause duplicates after ambiguous
responses; check Discord before retrying. Threads/forums are not destinations.
The dashboard API remains separate and publishes to explicitly selected channels.

## Tests

Run `python -m unittest discover -v` from this directory. Tests use fake Discord
sends and do not log in or publish real content. Validate the actual parent session
integration and an image/video upload in a test server before deployment.
