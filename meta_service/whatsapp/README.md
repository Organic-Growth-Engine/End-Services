# WhatsApp Service (Twilio Integration)

A Node.js & Express service for sending and receiving WhatsApp messages and media through the Twilio API.

---

## Features

- **Text Messaging:** Send outbound WhatsApp text messages (`POST /api/messages/text`).
- **Media Messaging:**
  - Send local image (JPEG, PNG) and video (MP4) files via multipart upload (`POST /api/messages/media`).
  - Send remotely hosted media via public URL (`POST /api/messages/media-url`).
- **Message Inspection:** Fetch outbound or inbound message details by Twilio SID (`GET /api/messages/:sid`).
- **Inbound Webhook Handling:**
  - Secure webhook endpoint (`POST /webhooks/twilio/inbound`) with Twilio HMAC-SHA1 signature validation.
  - Automatically downloads inbound media attachments and stores them locally in `./uploads`.
  - Responds with valid TwiML `<Response></Response>`.
- **Inbound Message Store:** Flat-file message persistence (`GET /api/inbound-messages` and `GET /api/inbound-messages/:sid`).
- **Development Simulator:** Test inbound message workflows locally without Twilio (`POST /api/dev/inbound`).
- **Health Check:** Service status and configuration report (`GET /health`).

---

## Directory Layout

```
meta_service/whatsapp/
├── data/              # Inbound message persistence (ignored by git)
├── postman/           # Postman collection & environment for testing
├── samples/           # Sample image and video files for testing
├── src/
│   ├── config/        # Environment and Twilio client configuration
│   ├── controllers/   # Request handlers for messages, webhooks, and health
│   ├── middleware/    # Error handling, 404, and Twilio signature verification
│   ├── routes/        # Express route definitions
│   ├── services/      # Business logic (message sending, media storage, inbound persistence)
│   ├── utils/         # Validation, phone formatting, logging, and helpers
│   ├── app.js         # Express app initialization
│   └── index.js       # Server entry point
├── test/              # Unit and integration test suite
├── uploads/           # Stored media files (ignored by git)
├── .env.example       # Example environment variables
├── package.json
└── README.md
```

---

## Getting Started

### 1. Installation

```bash
cd meta_service/whatsapp
npm install
```

### 2. Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Fill in your Twilio credentials and public URL:

```env
# Server
PORT=3000

# Public URL reachable by Twilio (e.g. your ngrok HTTPS URL)
PUBLIC_BASE_URL=https://your-domain.ngrok-free.app

# Twilio Credentials
TWILIO_ACCOUNT_SID=ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Optional Settings
TWILIO_VALIDATE_SIGNATURE=true
UPLOAD_TTL_MINUTES=60
INBOUND_STORE_LIMIT=500
MAX_IMAGE_BYTES=5242880
MAX_VIDEO_BYTES=16777216
MAX_TOTAL_MEDIA_BYTES=20971520
```

> **Note:** Twilio requires a public HTTPS URL (`PUBLIC_BASE_URL`) to fetch uploaded media and deliver webhooks. Use `ngrok http 3000` during local development.

### 3. Running the Service

- **Production:** `npm start`
- **Development (watch mode):** `npm run dev`
- **Expose via tunnel:** `npm run tunnel`
- **Run tests:** `npm test`

---

## API Endpoints

### Outbound Messages

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/messages/text` | Send a text message |
| `POST` | `/api/messages/media` | Upload and send a media file (`file`, `to`, `body`) |
| `POST` | `/api/messages/media-url` | Send media from a public URL (`mediaUrl`, `to`, `body`) |
| `GET` | `/api/messages/:sid` | Fetch message status from Twilio |

### Inbound Messages & Webhooks

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/webhooks/twilio/inbound` | Twilio inbound webhook handler |
| `GET` | `/api/inbound-messages` | List received messages |
| `GET` | `/api/inbound-messages/:sid` | Get a single received message |
| `POST` | `/api/dev/inbound` | Development-only inbound simulator |

### Media & System

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/media/:filename` | Serve locally stored media files |
| `GET` | `/health` | Service health status |

---

## Testing

Run the automated test suite with Node's native test runner:

```bash
npm test
```

A Postman collection and local environment are also provided in the [`postman/`](./postman/) directory.

