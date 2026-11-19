# End Services

Publishing services for YouTube, X, Telegram, Facebook, Instagram and Discord,
plus a **gateway**: one API call posts to all of them.

## Quick start

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/)
(`curl -LsSf https://astral.sh/uv/install.sh | sh`) and Python 3.12, which uv
installs for you if it's missing.

```bash
./setup.sh      # once: installs every service and creates .env
# fill in the credentials for the platforms you use in .env
./run.sh        # starts every configured service + the gateway
```

`run.sh` starts only the platforms whose credentials are filled in and says
what's missing for the others. Then post everywhere at once:

```bash
curl -X POST http://127.0.0.1:8080/posts \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello from End Services", "media": [{"type": "image", "url": "https://picsum.photos/1200/800.jpg"}]}'
# → {"id": "<job id>", "status": "running", ...}

curl http://127.0.0.1:8080/posts/<job id>    # result per platform
```

Or open <http://127.0.0.1:8080/docs> and try it in the browser.
`./run.sh telegram discord` starts only those platforms. Logs are in `.logs/`.

## Credentials

Everything lives in one file, `.env` at the repo root (created from
[`.env.example`](.env.example)), which every service reads. Each section of
the file says where to get its values; the service READMEs have step-by-step
guides:

| Platform  | What you need                                       | Guide                                                 |
| --------- | --------------------------------------------------- | ----------------------------------------------------- |
| YouTube   | OAuth client + refresh token (a script gets it)     | [youtube](youtube/README.md)                          |
| X         | API key/secret + access token/secret                | [x](x/README.md)                                      |
| Telegram  | Bot token + chat ids                                | [bot/telegram](bot/telegram/README.md)                |
| Facebook  | Page access token + Page id                         | [meta_service/facebook](meta_service/facebook/README.md) |
| Instagram | System User token + account id                      | [meta_service/instagram](meta_service/instagram/README.md) |
| Discord   | Bot token + channel ids                             | [bot/discord](bot/discord/README.md)                  |

`.env` is git-ignored. Never commit it.

## Services

| Folder                   | Port | Endpoint                                      |
| ------------------------ | ---- | --------------------------------------------- |
| `gateway/`               | 8080 | `POST /posts`, `GET /posts/{id}`: post everywhere ([docs](gateway/README.md)) |
| `x/`                     | 8000 | `POST /publish`                               |
| `youtube/`               | 8001 | `POST /upload`                                |
| `bot/telegram/`          | 8002 | `POST /publish` (+ the `/broadcast` chat bot) |
| `meta_service/facebook/` | 8003 | `POST /publish`                               |
| `meta_service/instagram/`| 8004 | `POST /publish`                               |
| `bot/discord/`           | 8005 | `POST /publish`                               |

`meta_service/whatsapp/` and `misc/` are placeholders.

The services have no authentication and download any media URL they're
given, so run them on an internal network and expose only what you need.

## Tests

Each service has its own tests, which fake the platform APIs (nothing is posted):

```bash
(cd gateway && uv run pytest)
(cd x && uv run pytest)
(cd bot/discord && uv run pytest)
(cd youtube && uv run python -m unittest discover tests)
```
