# Discord publisher

Requires Python 3.10 or newer.

1. Install dependencies: `python -m pip install -r requirements.txt`
2. Create `.env` beside `Discord_autobot.py` containing `BOT_TOKEN=your_bot_token`.
   No channel ID is needed. Never commit the token.
3. Invite the application with the `bot` and `applications.commands` scopes.
   Grant View Channel, Send Messages, Attach Files and Embed Links in destination
   channels. No privileged intents are required.
4. Run `python Discord_autobot.py` and keep it running.
   Global slash commands may take time to appear after the first start.

## Commands

- `/publish channel message media`: choose a text channel in the current server.
  Provide text, an attachment (image/video/audio), or both. At least one is required.
  The caller needs Manage Messages and permission to send in the chosen channel.
- `/broadcast message title thumbnail_url`: the bot application owner can invoke
  this from a server to send an embed to every server the bot has joined.
  Disnake checks application ownership (including its team ownership rules);
  server administrator status alone does not grant access.
  The thumbnail must be an HTTP(S) URL. Each server receives one copy in its
  system channel if usable, otherwise the first accessible text channel with
  Send Messages and Embed Links. Servers without a usable channel are skipped.
  A private summary reports sent and skipped/failed counts. One failed delivery
  does not stop the other servers.

Confirmations and errors are private. Mentions do not ping users or roles.
Errors are handled separately in `error_handler.py`.

## HTTP API

Running `python Discord_autobot.py` also starts an API at http://127.0.0.1:8080.
No API key is required. It binds to your own computer by default. Anyone who can
reach the API can post using the bot. Optional `.env` settings: `API_HOST` and
`API_PORT`. Slash commands remain available. No browser CORS access is enabled.

- `GET /health`: Discord connection status.
- `GET /channels`: joined servers and accessible text channels, with string IDs.
- `POST /publish`: JSON containing `channel_id` (string) and `message`.
  Alternatively multipart form fields `channel_id`, optional `message`, and
  one uploaded `media` file. Text is limited to 2000 characters. Uploads are
  limited to the smaller of 25 MiB and the Discord server's upload limit.
  Files are uploaded by the caller; server-side file paths and URL downloads
  are not accepted. No format conversion occurs.

PowerShell text example (replace the channel ID with one from `/channels`):

```powershell
Invoke-RestMethod http://127.0.0.1:8080/channels
Invoke-RestMethod http://127.0.0.1:8080/publish -Method Post -ContentType 'application/json' -Body '{"channel_id":"123456789012345678","message":"Hello from outside Discord!"}'
```

Media upload example:

```powershell
curl.exe http://127.0.0.1:8080/publish -F "channel_id=123456789012345678" -F "message=New video" -F "media=@C:\Videos\clip.mp4"
```

Successful publishing returns HTTP 201 with `message_id`, `channel_id`, and
`url`. Errors return JSON with `error` and an appropriate HTTP status. A 503
means Discord isn't connected yet. A failed/ambiguous delivery should be
checked in Discord before retrying: requests have no deduplication key.

Run mocked API checks: `python -m unittest test_api -v`.
