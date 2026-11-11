# Discord publisher

Requires Python 3.10 or newer.

1. Install dependencies: `python -m pip install -r requirements.txt`
2. Create `.env` beside `main.py` containing `BOT_TOKEN=your_bot_token`.
   No channel ID is needed. Never commit the token.
3. Invite the application with the `bot` and `applications.commands` scopes.
   Grant View Channel, Send Messages, Attach Files and Embed Links in destination
   channels. No privileged intents are required.
4. Run `python main.py` and keep it running.
   Global slash commands may take time to appear after the first start.

## Discord commands

- `/publish channel`: the **server owner** selects the one text channel that
  will receive announcements. The bot must have View Channel, Send Messages,
  and Embed Links permission. Running it again replaces the selection.
- `/unpublish`: the server owner disables announcements for that server.
- `/broadcast message title [thumbnail] [thumbnail_url]`: the **bot application
  owner** sends an embed to the selected channel in each subscribed server.
  Disnake checks application ownership (including its team ownership rules).
  Server administrator status does not grant access to these owner-only actions.

Servers start unsubscribed. There is no automatic system-channel or first-channel
fallback. Deleted or inaccessible selected channels are skipped; the server owner
must select a usable channel again. Choices persist in `channels.sqlite3` beside
`main.py`; keep this file on persistent storage and do not commit it.

Choose a PNG, JPG, GIF or WebP thumbnail upload (at most 25 MiB), or a direct,
publicly accessible HTTP(S) image URL. Choose only one. Uploads also require
Attach Files permission and must fit each destination server's upload limit.
Each subscribed server receives at most one copy per broadcast invocation.
A failed Discord delivery does not stop delivery to other servers. A private
summary reports sent and skipped/failed counts. Only one broadcast runs at a time.

Confirmations and errors are private. Mentions do not ping users or roles.
Publishing commands and delivery live in `publisher.py`; command errors are
handled separately in `error_handler.py`.

Migration: the old `/publish message title ...` command is now `/broadcast`.
Every server owner must opt in with `/publish channel` after upgrading.

## HTTP API

Running `python main.py` also starts an API at http://127.0.0.1:8080.
Set `DISCORD_API_SECRET` in `.env` to a strong random secret and send it in the
`X-API-Key` header on requests to `/channels` and `/publish`. If the secret is
blank, both routes return 503. The slash commands and `/health` remain available.
Optional `.env` settings are `API_HOST` and `API_PORT`. Use HTTPS if you expose
the API beyond your computer so the key stays private in transit.

- `GET /health`: Discord connection status.
- `GET /channels`: joined servers and accessible text channels, with string IDs.
- `POST /publish`: authenticated direct publishing to the supplied channel
  (separate from the opted-in slash-command broadcast). JSON containing `channel_id` (string) and `message`.
  Alternatively multipart form fields `channel_id`, optional `message`, and
  one uploaded `media` file. Text is limited to 2000 characters. Uploads are
  limited to the smaller of 25 MiB and the Discord server's upload limit.
  Files are uploaded by the caller; server-side file paths and URL downloads
  are not accepted. No format conversion occurs.

Set `DISCORD_API_SECRET` in your PowerShell session to match the server's
secret. Replace the channel ID below with one from `/channels`.

```powershell
$headers = @{ "X-API-Key" = $env:DISCORD_API_SECRET }
Invoke-RestMethod http://127.0.0.1:8080/channels -Headers $headers
Invoke-RestMethod http://127.0.0.1:8080/publish -Headers $headers -Method Post -ContentType 'application/json' -Body '{"channel_id":"123456789012345678","message":"Hello from outside Discord!"}'
```

Media upload example:

```powershell
curl.exe http://127.0.0.1:8080/publish -H "X-API-Key: $env:DISCORD_API_SECRET" -F "channel_id=123456789012345678" -F "message=New video" -F "media=@C:\Videos\clip.mp4"
```

Successful publishing returns HTTP 201 with `message_id`, `channel_id`, and
`url`. Errors return JSON with `error` and an appropriate HTTP status. A 503
means Discord isn't connected yet or HTTP publishing is disabled. A failed/ambiguous delivery should be
checked in Discord before retrying: requests have no deduplication key.

Run all mocked checks from this directory: `python -m unittest discover -v`.
These tests do not connect to Discord or send real announcements.
