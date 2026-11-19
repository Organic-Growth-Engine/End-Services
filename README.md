# Directory Structure
```bash
.
├── gateway        # one API that posts to every platform
├── bot
│   ├── discord
│   └── telegram
├── meta_service
│   ├── facebook
│   ├── instagram
│   └── whatsapp
├── misc
└── youtube
```

## Posting gateway

`POST /posts` on the [gateway](gateway/README.md) publishes one post to YouTube,
X and Telegram at once and reports the result per platform.

## YouTube upload component

See [YouTube setup and upload instructions](youtube/README.md). The component exposes
POST `/upload`, which downloads a video from a URL and uploads it with the channel
OAuth credentials sent in the request.
