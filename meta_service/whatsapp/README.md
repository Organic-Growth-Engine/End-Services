# WhatsApp Service

A FastAPI service that sends messages to WhatsApp users through the
[WhatsApp Business Cloud API](https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform).

## Modules

| Module               | Purpose                                                                        |
| -------------------- | ------------------------------------------------------------------------------ |
| `main.py`            | FastAPI app, router registration, `WhatsAppError` → HTTP 502 handler           |
| `routes.py`          | HTTP routes and dependency injection                                           |
| `schemas.py`         | Pydantic request/response models and local validation                          |
| `config.py`          | Loads `WA_*` settings from `.env`                                              |
| `whatsapp_client.py` | `WhatsAppClient` - async wrapper over the Messages, Media and Templates APIs   |
| `publisher.py`       | `WhatsAppPublisher` - resolves media and sends to each recipient independently |

## Setup

```bash
uv sync
cp .env.example .env  # then fill in the token, phone number id and WABA id
uv run uvicorn main:app --reload
```

You need a Meta app, a WhatsApp Business Account (Messaging account), a business
phone number ID, and a system user token with:

- `whatsapp_business_messaging` - send messages
- `whatsapp_business_management` - list templates and read phone metadata

Recipients must have opted in to receive messages from your business. Note that
a template must be approved by Meta before it can be used, and that free-form
messages are only allowed while a 24-hour customer service window is open.

Interactive docs: <http://127.0.0.1:8000/docs>

## Routes

| Method | Path            | Purpose                                          |
| ------ | --------------- | ------------------------------------------------ |
| GET    | `/health`       | Health check                                     |
| GET    | `/phone-number` | Connected number, messaging limit and throughput |
| GET    | `/templates`    | Templates in the WABA (defaults to `APPROVED`)   |
| POST   | `/publish`      | Send a message to 1-50 recipients                |

## Publishing

```bash
curl -X POST http://127.0.0.1:8000/publish \
  -H 'Content-Type: application/json' \
  -d '{
    "to": ["+16505551234", "+919876543210"],
    "message": {"type": "text", "body": "Hello from the social media manager!"}
  }'
```

Supported `message` objects:

```json
{ "type": "text", "body": "Hi!", "preview_url": false }
```

```json
{
	"type": "template",
	"name": "order_confirmation",
	"language": "en_US",
	"components": [
		{
			"type": "body",
			"parameters": [{ "type": "text", "parameter_name": "first_name", "text": "Jessica" }]
		}
	]
}
```

```json
{ "type": "image", "url": "https://example.com/photo.jpg", "caption": "Optional" }
{ "type": "video", "media_id": "1234567890", "caption": "Optional" }
{ "type": "audio", "url": "https://example.com/voice.mp3" }
{ "type": "document", "url": "https://example.com/invoice.pdf", "filename": "invoice.pdf" }
```

Every media message needs exactly one of `url` or `media_id`. When a `url` is
provided the service downloads it and uploads the asset to Meta, then sends the
resulting `media_id`; `mime_type` and `filename` can override the defaults.
Uploaded media IDs are valid for 30 days.

A successful call returns one receipt per recipient. Failures are reported
per recipient so one bad number does not discard a whole broadcast:

```json
{
	"messages": [
		{
			"to": "+16505551234",
			"wa_id": "16505551234",
			"message_id": "wamid.HB..."
		}
	],
	"failures": [],
	"media_ids": [],
	"warnings": []
}
```

`message_id` only means Meta **accepted** the message; it is not a delivery
confirmation.

Validation failures return FastAPI's structured `422` response. Graph API
failures return `502` with `{"detail": "..."}`.

## Limits

Enforced locally by the schemas:

- Recipients: 1-50 E.164 numbers per request.
- Text body: 4,096 characters. Captions: 1,024 characters.
- Media: one of `url` / `media_id`; size caps on upload (image 5 MB, video and
  audio 16 MB, document 100 MB); MIME prefix checked against the message type.
- Templates: lowercase name (`^[a-z0-9_]{1,512}$`), language code, consistent
  named or positional parameters, button components need `sub_type` and `index`.

Enforced by WhatsApp:

- Free-form messages require an open 24-hour customer service window; outside
  it only approved templates can be sent. Opt-in is required either way.
- Message limits (250 unique users per rolling 24 hours for new portfolios),
  throughput (80 msg/s by default), template quality rating/pacing/pausing and
  per-user pair limits. Known error codes are surfaced in `warnings`.
- Pricing is per delivered message by category and recipient market; each
  number gets 1,000 free service messages per month.
- Message order is not guaranteed; do not rely on sequential sends arriving in
  order.
