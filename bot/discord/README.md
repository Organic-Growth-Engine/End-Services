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

## Discord command

- `/publish message title [thumbnail] [thumbnail_url]`: the bot application owner can invoke
  this from a server to send an embed to every server the bot has joined.
  Disnake checks application ownership (including its team ownership rules);
  server administrator status alone does not grant access.
  Choose a local PNG, JPG, GIF or WebP file in the optional `thumbnail` field
  (up to 25 MiB), or supply a direct, publicly accessible image URL in
  `thumbnail_url`. Choose only one. Uploaded thumbnails require Attach Files
  permission and must fit each destination server's upload limit. Each server receives one copy in its
  system channel if usable, otherwise the first accessible text channel with
  Send Messages and Embed Links. Servers without a usable channel are skipped.
  A private summary reports sent and skipped/failed counts. One failed delivery
  does not stop the other servers.

Confirmations and errors are private. Mentions do not ping users or roles.
Errors are handled separately in `error_handler.py`.

## HTTP API

Running `python Discord_autobot.py` also starts an API at http://127.0.0.1:8080.
Set `DISCORD_API_SECRET` in `.env` to a strong random secret and send it in the
`X-API-Key` header on requests to `/channels` and `/publish`. If the secret is
blank, both routes return 503. The `/publish` command and `/health` remain available.
Optional `.env` settings are `API_HOST` and `API_PORT`. Use HTTPS if you expose
the API beyond your computer so the key stays private in transit.

- `GET /health`: Discord connection status.
- `GET /channels`: joined servers and accessible text channels, with string IDs.
- `POST /publish`: JSON containing `channel_id` (string) and `message`.
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

Run mocked API checks: `python -m unittest test_api -v`.
