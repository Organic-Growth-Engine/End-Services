# SPECDOC — Twilio WhatsApp Integration Service

A minimal Express backend for sending and receiving WhatsApp messages through Twilio,
with SQLite persistence for inbound messages and filesystem storage for media.

- **Runtime:** Node >= 20 (developed on 22.17)
- **Stack:** Express 5, Multer 2, Axios, Twilio SDK 6, `node:sqlite`
- **Entry point:** `src/index.js` (`npm start` / `npm run dev`)
- **Test suite:** `npm test` (node:test + supertest, 35 tests)

---

## 1. Architecture overview

```
src/
├── index.js                 # Server entry point: boots app, starts cleanup job, graceful shutdown
├── app.js                   # Express app factory: parsers, /media static route, routes, error chain
├── config/
│   ├── env.js               # Environment variable loading + validation (single `config` object)
│   ├── constants.js         # Code-level constants: MULTER, MESSAGE, HTTP groups
│   └── twilio.js            # Lazy singleton Twilio REST client
├── routes/
│   ├── index.js             # Route registry (/health, /webhooks, /api/*, dev simulator)
│   ├── messages.js          # Outbound message routes (/api/messages)
│   ├── webhooks.js          # Twilio webhook routes (/webhooks/twilio)
│   └── inboundMessages.js   # Stored inbound message routes (/api/inbound-messages)
├── controllers/
│   ├── messageController.js     # Outbound send/get handlers
│   ├── webhookController.js     # Inbound webhook + simulator handlers
│   ├── inboundMessageController.js # Stored inbound read handlers
│   └── healthController.js      # /health handler
├── middleware/
│   ├── twilioSignature.js   # X-Twilio-Signature validation middleware
│   ├── errorHandler.js      # Central error-to-HTTP-JSON mapper
│   └── notFound.js          # 404 fallback
├── services/
│   ├── messageService.js        # Twilio message create/fetch + error mapping + serialization
│   ├── mediaService.js          # Media persistence, Twilio media download, TTL cleanup
│   └── inboundMessageService.js # Webhook payload parse + media resolve + persist orchestration
├── db/
│   ├── connection.js        # SQLite lifecycle: connection, WAL, schema, legacy migration, close
│   └── inboundStore.js      # CRUD operations for inbound messages (data access layer)
└── utils/
    ├── logger.js        # JSON line logger (stdout/stderr)
    ├── httpError.js     # HttpError class
    ├── validation.js    # Request field validators
    ├── phone.js         # WhatsApp/E.164 address parsing
    ├── media.js         # MIME detection, safe URL checks, filename creation
    └── twiml.js         # TwiML XML builders
```

**Request flow (inbound):** Twilio → `POST /webhooks/twilio/inbound` → `requireTwilioSignature`
(middleware) → `handleInbound` (controller) → `recordInbound` (service) → parse + download media +
`inboundStore.add` (SQLite) → empty TwiML response.

**Request flow (outbound):** client → `POST /api/messages/...` → controller validation →
`messageService` → Twilio SDK → serialized JSON response.

---

## 2. HTTP API

Base URL: `http://localhost:{PORT}` (defaults 3000). All error responses share the shape:

```json
{ "error": { "code": "ERROR_CODE", "message": "human readable", "details": {} } }
```

| # | Method | Path | Purpose | Middleware | Handler |
|---|--------|------|---------|-----------|---------|
| 1 | GET | `/health` | Service health/config snapshot | – | `healthController.getHealth` |
| 2 | POST | `/api/messages/text` | Send a WhatsApp text message | – | `messageController.sendText` |
| 3 | POST | `/api/messages/media` | Send uploaded media (multipart) | Multer (`file` field, memory storage) | `messageController.sendMedia` |
| 4 | POST | `/api/messages/media-url` | Send hosted media by URL | – | `messageController.sendMediaUrl` |
| 5 | GET | `/api/messages/:sid` | Fetch a message from Twilio | – | `messageController.getMessage` |
| 6 | GET | `/api/inbound-messages` | List stored inbound messages | – | `inboundMessageController.listInbound` |
| 7 | GET | `/api/inbound-messages/:sid` | Get one stored inbound message | – | `inboundMessageController.getInbound` |
| 8 | POST | `/webhooks/twilio/inbound` | Twilio inbound webhook | `requireTwilioSignature` | `webhookController.handleInbound` |
| 9 | POST | `/api/dev/inbound` | Dev-only inbound simulator | – (registered only when `ENABLE_INBOUND_SIMULATOR`) | `webhookController.simulateInbound` |
| 10 | GET | `/media/:filename` | Serve stored media files | inline header middleware | `express.static(uploadDir)` |

Any unmatched route → `notFound` middleware → 404 `NOT_FOUND`.

### 2.1 `GET /health`

Response `200`:
```json
{
  "status": "ok",
  "uptimeSeconds": 120,
  "twilioConfigured": true,
  "signatureValidationEnabled": true,
  "publicBaseUrlConfigured": true,
  "inboundSimulatorEnabled": true,
  "timestamp": "2026-11-12T09:48:26.383Z"
}
```
No secrets are exposed.

### 2.2 `POST /api/messages/text`

Request JSON body:
| Field | Type | Required | Rules |
|---|---|---|---|
| `to` | string | yes | E.164 (`+15551234567`) or `whatsapp:+15551234567`; spaces/`().-` tolerated |
| `body` | string | yes | trimmed, non-empty, ≤ 1600 chars (`MESSAGE.MAX_TEXT_LENGTH`) |

Response `201`:
```json
{ "message": { "sid": "SM...", "status": "queued", "direction": "outbound-api",
  "to": "whatsapp:+15551234567", "from": "whatsapp:+14155238886", "body": "hello",
  "numSegments": "1", "numMedia": "0", "mediaUrls": [],
  "dateCreated": "2026-11-12T...", "dateUpdated": null,
  "errorCode": null, "errorMessage": null } }
```

Errors: `TWILIO_NOT_CONFIGURED` (503), `INVALID_PHONE_NUMBER` (400), `INVALID_BODY` (400),
`TWILIO_AUTH_FAILED` (502), `TWILIO_RATE_LIMITED` (429), `TWILIO_REJECTED` (400),
`TWILIO_UNAVAILABLE` (502).

### 2.3 `POST /api/messages/media`

`multipart/form-data`:
| Field | Type | Required | Rules |
|---|---|---|---|
| `to` | string | yes | as 2.2 |
| `body` | string | no | optional caption, trimmed, ≤ 1600 chars |
| `file` | file | yes | JPEG/PNG (≤ `maxImageBytes`, default 5 MB) or MP4 (≤ `maxVideoBytes`, default 16 MB); magic-byte verified |

Multer limits (constants `MULTER`): 1 file, ≤ 10 fields, ≤ 12 parts, `fileSize` = `maxVideoBytes`.
The file is validated by magic bytes, persisted to `uploads/<16-hex>.<ext>`, and Twilio is given
`{PUBLIC_BASE_URL}/media/<filename>` as the media URL.

Response `201`: `{ "message": {...}, "media": { "url", "contentType", "kind", "size" } }`.

Errors: as 2.2 plus `MEDIA_FILE_REQUIRED` (400), `INVALID_MEDIA_TYPE` (400), `MEDIA_TOO_LARGE`
(413), `FILE_TOO_LARGE` (413 Multer), `UNEXPECTED_FILE` (400), `TOO_MANY_FILES` (400),
`INVALID_MULTIPART` (400), `PUBLIC_BASE_URL_NOT_CONFIGURED` (503).

### 2.4 `POST /api/messages/media-url`

Request JSON body:
| Field | Type | Required | Rules |
|---|---|---|---|
| `to` | string | yes | as 2.2 |
| `mediaUrl` | string | yes | http(s) URL, ≤ 4096 chars (`MESSAGE.MAX_MEDIA_URL_LENGTH`) |
| `body` | string | no | optional caption |

Response `201`: `{ "message": { ..., "mediaUrls": ["https://example.com/clip.mp4"] } }`.

Errors: as 2.2 plus `INVALID_MEDIA_URL` (400).

### 2.5 `GET /api/messages/:sid`

Path param `sid`: Twilio message SID, `SM`/`MM` + 32 hex chars.
Response `200`: `{ "message": {...} }` (same shape as 2.2, fetched live from Twilio).

Errors: `INVALID_MESSAGE_SID` (400), `TWILIO_RESOURCE_NOT_FOUND` (404), auth/rate/reject/unavailable as 2.2.

### 2.6 `GET /api/inbound-messages`

Query params:
| Param | Type | Default | Rules |
|---|---|---|---|
| `limit` | int | 50 | clamped to 1–100 |
| `before` | string | – | ISO timestamp cursor; returns messages strictly older |

Response `200`:
```json
{ "messages": [ { "sid": "...", "direction": "inbound", ..., "receivedAt": "..." } ],
  "nextCursor": "2026-11-05T18:17:46.187Z" | null }
```
`nextCursor` is the `receivedAt` of the last returned message when more pages exist; feed it back
as `before` to paginate. Ordering: newest first (`received_at DESC, sid DESC`).

### 2.7 `GET /api/inbound-messages/:sid`

Path param `sid`: same SID pattern. Response `200`: `{ "message": {...} }` — the full stored
message object, including `media[]` items with `localUrl` and download `status`.

Errors: `INVALID_MESSAGE_SID` (400), `INBOUND_MESSAGE_NOT_FOUND` (404).

### 2.8 `POST /webhooks/twilio/inbound`

Twilio sends `application/x-www-form-urlencoded` webhook payloads. Requires a valid
`X-Twilio-Signature` header computed over `{PUBLIC_BASE_URL}{request URL}` (HMAC via Twilio SDK,
validated against `TWILIO_AUTH_TOKEN`). Signature validation can be disabled via
`TWILIO_VALIDATE_SIGNATURE=false` (not for production).

Expected form fields (subset consumed):
`MessageSid`/`SmsMessageSid`, `From`, `To`, `Body`, `NumMedia`, `MediaUrl0..N`,
`MediaContentType0..N`, `ProfileName`, `WaId`, `ExternalUserId`, `Username`, `NumSegments`,
`MessageStatus`/`SmsStatus`.

Behavior:
- Validates SID, parses fields, downloads up to `MESSAGE.MAX_INBOUND_MEDIA` (10) allowed media
  items from Twilio (with basic auth on Twilio URLs), stores the full message in SQLite,
  deduplicating by SID (Twilio may redeliver).
- Unsupported media content types are marked `status: "ignored"` without downloading; failed
  downloads are marked `status: "failed"` with an `error`.

Response `200`: `text/xml` — `<?xml version="1.0" encoding="UTF-8"?><Response></Response>`
(empty TwiML = no auto-reply).

Errors: `INVALID_MESSAGE_SID` (400), `INVALID_TWILIO_SIGNATURE` (403),
`TWILIO_NOT_CONFIGURED` (503), `PUBLIC_BASE_URL_NOT_CONFIGURED` (503).

### 2.9 `POST /api/dev/inbound` (development only)

Registered only when `ENABLE_INBOUND_SIMULATOR=true` (default outside production). Accepts the
same JSON-ish payload as 2.8, records the message, and returns `200 { "message": {...} }` instead
of TwiML. Used by tests and local development to simulate Twilio deliveries.

### 2.10 `GET /media/:filename`

Serves files from `config.uploadDir` (`uploads/` by default) via `express.static`:
- `X-Content-Type-Options: nosniff` and `Content-Disposition: inline; filename="<basename>"` are
  set on every response (browser displays the file; uploaded content cannot execute as a page)
- `index: false`, `dotfiles: 'ignore'`, `fallthrough: true`, `Cache-Control max-age`
  = `MEDIA_CACHE_MAX_AGE` (default `1h`)

Consumed by Twilio (fetching outbound media) and by clients viewing stored inbound media.

---

## 3. Controllers

Controllers receive `(req, res, next)`, validate inputs, delegate to services, and either send a
response or forward errors via `next(err)`.

### `src/controllers/webhookController.js`
| Function | Parameters | Returns / behavior |
|---|---|---|
| `handleInbound(req, res, next)` | `req.body` — Twilio form payload | `await recordInbound(req.body)`; responds `200 text/xml` empty TwiML; errors → `next(err)` |
| `simulateInbound(req, res, next)` | `req.body` — simulated payload | `await recordInbound(req.body)`; responds `200 JSON { message }` |

### `src/controllers/messageController.js`
| Function | Parameters | Returns / behavior |
|---|---|---|
| `sendText(req, res, next)` | body `{ to, body }` | validates address + text; `messageService.sendTextMessage`; `201 { message }` |
| `sendMedia(req, res, next)` | multipart `{ to, body?, file }` | validates; `mediaService.saveUploadedMedia` + `messageService.sendMediaMessage`; `201 { message, media }` |
| `sendMediaUrl(req, res, next)` | body `{ to, mediaUrl, body? }` | validates; `messageService.sendMediaMessage`; `201 { message }` |
| `getMessage(req, res, next)` | `req.params.sid` | validates SID; `messageService.fetchMessage`; `200 { message }` |

### `src/controllers/inboundMessageController.js`
| Function | Parameters | Returns / behavior |
|---|---|---|
| `listInbound(req, res, next)` | query `{ limit?, before? }` | `inboundStore.list({ limit, before })`; `200 { messages, nextCursor }` |
| `getInbound(req, res, next)` | `req.params.sid` | `inboundStore.get(sid)`; `200 { message }` or `404 INBOUND_MESSAGE_NOT_FOUND` |

### `src/controllers/healthController.js`
| Function | Parameters | Returns / behavior |
|---|---|---|
| `getHealth(req, res)` | – | `200` config snapshot (see 2.1); no secrets |

---

## 4. Middleware

Middleware runs before handlers, terminates via `next()` / `next(err)`, and never writes a
response itself (except `errorHandler`, which is terminal).

### `src/middleware/twilioSignature.js`
| Function | Parameters | Behavior |
|---|---|---|
| `requireTwilioSignature(req, res, next)` | Express req/res/next | If `validateSignature=false` → pass through. If Twilio/PUBLIC_BASE_URL unconfigured → `next(HttpError 503)`. Missing header → `403 INVALID_TWILIO_SIGNATURE`. Validates `X-Twilio-Signature` via `twilio.validateRequest(authToken, signature, publicBaseUrl + originalUrl, body)`; invalid → `403`; valid → `next()`. |

### `src/middleware/errorHandler.js`
| Function | Parameters | Behavior |
|---|---|---|
| `describeBodyParserError(err)` | error | Maps `entity.parse.failed` → 400 `INVALID_JSON`; `entity.too.large` → 413 `PAYLOAD_TOO_LARGE`; else null |
| `describeMulterError(err)` | error | Maps `MulterError` codes: `LIMIT_FILE_SIZE` → 413 `FILE_TOO_LARGE`; `LIMIT_UNEXPECTED_FILE` → 400 `UNEXPECTED_FILE`; `LIMIT_FILE_COUNT` → 400 `TOO_MANY_FILES`; other → 400 `INVALID_MULTIPART`; else null |
| `errorHandler(err, req, res, next)` | Express 4-arg error signature | If headers sent → `next(err)`. Resolves status/code/message (HttpError code used as-is; 5xx messages masked as `Internal server error`; logs 5xx as error with stack in non-production, 4xx as warn). Responds `{ error: { code, message, details? } }` |

### `src/middleware/notFound.js`
| Function | Parameters | Behavior |
|---|---|---|
| `notFound(req, res, next)` | Express req/res/next | `next(HttpError 404 NOT_FOUND)` with `Route not found: {METHOD} {url}` |

---

## 5. Services

### `src/services/messageService.js` — outbound Twilio messaging
| Function | Parameters | Returns / behavior |
|---|---|---|
| `toIsoString(value)` | Date or date-like | ISO string or null |
| `serializeMessage(message)` | Twilio message object | Safe DTO: `sid, status, direction, to, from, body, numSegments, numMedia, mediaUrls[], dateCreated, dateUpdated, errorCode, errorMessage` (null-safe) |
| `mapTwilioError(err)` | Twilio/SDK error | 404 → `TWILIO_RESOURCE_NOT_FOUND` (404); 401/403 → `TWILIO_AUTH_FAILED` (502); 429 → `TWILIO_RATE_LIMITED` (429); other 4xx → `TWILIO_REJECTED` (400, with `twilioCode/status/message/moreInfo` details); else → `TWILIO_UNAVAILABLE` (502). HttpError passes through |
| `sendTextMessage({ to, body })` | validated address + text | `client.messages.create({ from: config.whatsappNumber, to, body })` → serialized |
| `sendMediaMessage({ to, body, mediaUrl })` | address, optional caption, media URL | `client.messages.create({ from, to, mediaUrl: [mediaUrl], body? })` → serialized with `mediaUrls: [mediaUrl]` |
| `fetchMessage(sid)` | Twilio SID | `client.messages(sid).fetch()` → serialized |

### `src/services/mediaService.js` — media persistence, download, cleanup
| Function | Parameters | Returns / behavior |
|---|---|---|
| `ensureUploadDir()` | – | creates `config.uploadDir` recursively |
| `buildPublicMediaUrl(filename)` | filename | `{PUBLIC_BASE_URL}/media/{filename}` or null if unconfigured |
| `requirePublicMediaUrl(filename)` | filename | as above, but throws `503 PUBLIC_BASE_URL_NOT_CONFIGURED` |
| `maxBytesFor(kind)` | `'image' \| 'video'` | `config.maxImageBytes` or `config.maxVideoBytes` |
| `persistMediaBuffer(buffer, { requirePublicUrl = false })` | raw media Buffer | Detects content type by magic bytes (JPEG/PNG/MP4 only) → `400 INVALID_MEDIA_TYPE`; enforces per-kind and total byte caps → `413 MEDIA_TOO_LARGE`; writes `uploads/<16-hex>.<ext>`; returns `{ filename, contentType, kind, size, localUrl }` |
| `saveUploadedMedia({ buffer })` | uploaded file buffer | `persistMediaBuffer` with `requirePublicUrl: true` (public URL mandatory for outbound sends) |
| `downloadInboundMedia(media)` | `{ url, contentType? }` | Guards: missing URL → failed; unsafe URL (private/loopback host) → failed; Twilio unconfigured → failed. Downloads via Axios (`timeout = mediaDownloadTimeoutMs`, max content length = `maxVideoBytes`, ≤ `HTTP.MEDIA_MAX_REDIRECTS` redirects, basic auth for `*.twilio.com` hosts), re-verifies magic bytes, persists, returns `{ url, contentType, declaredContentType, localUrl, status: 'downloaded', size }` — or `{ ..., status: 'failed', error }` on failure (logged warn) |
| `cleanupExpiredMedia()` | – | Deletes files in `uploadDir` (except `.gitkeep`) older than `UPLOAD_TTL_MINUTES`; returns removed count |
| `startMediaCleanup()` | – | Runs cleanup immediately + on `setInterval(config.mediaCleanupIntervalMs)`; timer `unref()`ed; returns timer |

### `src/services/inboundMessageService.js` — inbound webhook orchestration
| Function | Parameters | Returns / behavior |
|---|---|---|
| `parseInboundPayload(payload)` | Twilio webhook body | Validates SID against `MESSAGE.SID_PATTERN` → throws `400 INVALID_MESSAGE_SID`; caps media at `MESSAGE.MAX_INBOUND_MEDIA`; builds per-item `{ url, contentType, localUrl: null, status: 'pending'|'ignored' }` (ignored = unsupported MIME); returns message object: `{ sid, direction: 'inbound', status, from, to, body, profileName, waId, externalUserId, username, numSegments, numMedia (string), media[], receivedAt }` |
| `resolveMedia(message)` | parsed message | If an existing stored message already downloaded the same media URL, reuse it (idempotent redelivery); ignored items pass through; otherwise `mediaService.downloadInboundMedia` |
| `recordInbound(payload)` | webhook body | `parseInboundPayload` → `resolveMedia` → `inboundStore.add` (upsert, dedupe by SID) |

---

## 6. Data layer (`src/db/`)

The data layer is separated from business services: `connection.js` owns the database
lifecycle; `inboundStore.js` is pure data access (repository pattern). Consumers
(`inboundMessageService.js`, `inboundMessageController.js`) only ever import
`src/db/inboundStore.js`.

### `src/db/connection.js` — database lifecycle
Backed by `node:sqlite` (`DatabaseSync`), WAL mode, single lazily-opened connection at
`config.inboundDbFile` (default `data/whatsapp.db`). On first init, a legacy
`inbound-messages.json` file (if present next to the DB) is imported row-by-row and renamed
`.migrated`.

| Function | Parameters | Returns / behavior |
|---|---|---|
| `openDatabase()` (internal) | – | `mkdir` of the DB directory, `new DatabaseSync(config.inboundDbFile)`, `PRAGMA journal_mode = WAL`, apply `SCHEMA` |
| `migrateLegacyFile(database)` (internal) | open DatabaseSync | Reads legacy JSON store, upserts each row (`sid`, `receivedAt`, serialized message), logs imported count, renames file to `inbound-messages.json.migrated`; silently no-ops when the file does not exist (`ENOENT`) |
| `ensureDb()` | – | Returns the open connection; performs one-time init on first call (init promise cached; reset on failure) |
| `close()` | – | Closes the connection, resets init state (used by tests before temp-file cleanup) |

Future schema changes will be handled here via a `user_version`-based migration framework
(see §10).

### `src/db/inboundStore.js` — CRUD operations

**Table: `inbound_messages`**

```sql
CREATE TABLE inbound_messages (
  sid         TEXT PRIMARY KEY,
  received_at TEXT NOT NULL,
  payload     TEXT NOT NULL
);
CREATE INDEX idx_inbound_received_at
  ON inbound_messages (received_at DESC, sid DESC);
```

**Columns:**

| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `sid` | TEXT | PRIMARY KEY | Twilio message SID (`SM`/`MM` + 32 hex). Uniqueness enforces webhook dedupe: Twilio may redeliver the same message, and the upsert collapses duplicates into one row. Also the PK lookup for `get()` and `GET /api/inbound-messages/:sid` |
| `received_at` | TEXT | NOT NULL | ISO 8601 ingest timestamp (when the webhook was processed). The pagination key: `list()` orders by it descending and uses it as the `before` cursor. `sid` is the deterministic tiebreak for identical timestamps |
| `payload` | TEXT | NOT NULL | The complete message object serialized as JSON (lossless wide-JSON design — see below) |

**Index: `idx_inbound_received_at`** — covering index for the only non-PK query path
(`ORDER BY received_at DESC, sid DESC`), so pagination is an index scan even with millions of
rows.

**What the `payload` JSON contains** (built by `inboundMessageService.parseInboundPayload`,
§2.8 field list):

```json
{
  "sid": "SMf5623d4ad28c9e924225276b13676202",
  "direction": "inbound",
  "status": "received",
  "from": "whatsapp:+919971698891",
  "to": "whatsapp:+17372508034",
  "body": "join twilio-trial",
  "profileName": "Nezaal",
  "waId": "919971698891",
  "externalUserId": "whatsapp:IN.1136318448795975",
  "username": null,
  "numSegments": "1",
  "numMedia": "0",
  "media": [],
  "receivedAt": "2026-11-05T18:17:46.187Z"
}
```

`media[]` items carry `{ url, contentType, declaredContentType?, localUrl, status, size?, error? }`
with `status` ∈ `pending | downloaded | failed | ignored`.

**Design rationale:** only `sid` (PK) and `received_at` (indexed) are ever queried; all other
fields ride inside `payload` JSON, so adding new message fields requires no schema change.
Promoting fields to real indexed columns is the planned evolution when per-field querying
becomes a requirement (§10).

**Row retention:** after every `add()`, rows beyond `config.inboundStoreLimit` (default 500)
are deleted oldest-first — the table acts as a ring buffer, not an archive.

**Operations:**

| Function | Parameters | Returns / behavior |
|---|---|---|
| `add(message)` | message object | Upsert (`INSERT ... ON CONFLICT(sid) DO UPDATE`); then trims rows beyond `config.inboundStoreLimit` (oldest first); returns message |
| `get(sid)` | SID string | Row by PK → `JSON.parse(payload)`; null if absent |
| `list({ limit = 50, before })` | pagination options | `WHERE received_at < before ORDER BY received_at DESC, sid DESC LIMIT limit`; clamps limit 1–100; returns `{ messages, nextCursor }` (`nextCursor` = last `receivedAt` when more rows exist, else null) |
| `clear()` | – | `DELETE FROM inbound_messages` |
| `flush()` | – | Awaits initialization (writes are synchronous on the open connection); API-compat no-op |
| `close()` | – | Re-export of `connection.close()` (test convenience) |

---

## 7. Utilities

### `src/utils/logger.js`
JSON-lines logger to console. Every entry: `{ time, level, message, ...meta }`.
| Function | Parameters | Behavior |
|---|---|---|
| `info(message, meta?)` | string, object | `console.log(JSON line)` |
| `warn(message, meta?)` | string, object | `console.warn` |
| `error(message, meta?)` | string, object | `console.error` |

### `src/utils/httpError.js`
| Export | Definition |
|---|---|
| `class HttpError` | `constructor(statusCode, code, message, details?)` — extends `Error`; carries HTTP status, machine `code`, optional `details` (surfaced in error responses) |

### `src/utils/validation.js`
All throw `HttpError 400` with a machine code on failure; shared constants come from
`config/constants.js` (`MESSAGE.MAX_TEXT_LENGTH = 1600`, `MAX_MEDIA_URL_LENGTH = 4096`,
`SID_PATTERN`).
| Function | Parameters | Behavior |
|---|---|---|
| `requireWhatsAppAddress(value, field)` | raw string, field name | Parses via `phone.parseWhatsAppAddress`; error `INVALID_PHONE_NUMBER`; returns canonical `whatsapp:+E164` |
| `requireTextBody(value, field)` | raw string, field name | String + trimmed non-empty + ≤ 1600 chars; error `INVALID_BODY`; returns trimmed body |
| `optionalTextBody(value, field)` | raw string, field name | Same as above but `undefined`/`null` → `undefined` (empty after trim → `undefined`) |
| `requireMediaUrl(value, field)` | raw string, field name | http(s) URL ≤ 4096 chars, parseable; error `INVALID_MEDIA_URL`; returns normalized URL string |
| `requireMessageSid(value)` | raw string | `SM|MM` + 32 hex chars; error `INVALID_MESSAGE_SID`; returns trimmed SID |

### `src/utils/phone.js`
| Function | Parameters | Behavior |
|---|---|---|
| `parseWhatsAppAddress(value)` | raw string | Strips `whatsapp:` prefix and `[\s().-]`, validates against E.164 (`^\+[1-9]\d{6,14}$`); returns `{ e164, whatsapp: 'whatsapp:'+e164 }` or null |

### `src/utils/media.js`
| Function | Parameters | Behavior |
|---|---|---|
| `normalizeMimeType(value)` | raw string | Lowercase, strips `;params`, maps `image/jpg` → `image/jpeg`; null if invalid |
| `isAllowedMimeType(value)` | raw string | true only for `image/jpeg`, `image/png`, `video/mp4` |
| `mediaKind(value)` | raw string | `'image' \| 'video'` or null |
| `extensionForMime(value)` | raw string | `'jpg' \| 'png' \| 'mp4'` or null |
| `createMediaFilename(mimeType)` | MIME string | `<8 random bytes as 16 hex>.<ext>`; throws on unsupported type |
| `detectMediaType(buffer)` | Buffer | Magic-byte detection: JPEG (`FF D8 FF`), PNG signature, MP4 (`ftyp` at offset 4); null otherwise. Note: declared MIME is never trusted |
| `isTwilioMediaUrl(value)` | URL string | https + host `api.twilio.com`, `media.twiliocdn.com`, or `*.twilio.com` |
| `isSafeRemoteMediaUrl(value)` | URL string | Rejects non-http(s), localhost, `127.*`, `10.*`, `192.168.*`, `172.16–31.*`, `[::1]`, `*.local`, `*.internal` (SSRF protection for inbound downloads) |

### `src/utils/twiml.js`
| Function | Parameters | Behavior |
|---|---|---|
| `emptyTwimlResponse()` | – | `'<?xml version="1.0" encoding="UTF-8"?><Response></Response>'` |

---

## 8. Configuration

### `src/config/env.js` — `config` object (all env-driven)
| Key | Env var | Default | Meaning |
|---|---|---|---|
| `port` | `PORT` | 3000 | HTTP listen port |
| `publicBaseUrl` | `PUBLIC_BASE_URL` | '' | Public HTTPS URL (ngrok) Twilio can reach; trailing slashes trimmed |
| `accountSid` / `authToken` | `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | '' | Twilio credentials |
| `whatsappNumber` | `TWILIO_WHATSAPP_NUMBER` | '' | Sender number, parsed to `whatsapp:+E164` |
| `validateSignature` | `TWILIO_VALIDATE_SIGNATURE` | true | Webhook signature validation toggle |
| `uploadTtlMinutes` | `UPLOAD_TTL_MINUTES` | 60 | Media file TTL for cleanup |
| `uploadDir` | `MEDIA_UPLOAD_DIR` | `uploads` | Media storage directory |
| `mediaCleanupIntervalMs` | `MEDIA_CLEANUP_INTERVAL_MS` | 300000 | Cleanup job interval |
| `mediaDownloadTimeoutMs` | `MEDIA_DOWNLOAD_TIMEOUT_MS` | 10000 | Axios timeout for Twilio media downloads |
| `mediaCacheMaxAge` | `MEDIA_CACHE_MAX_AGE` | `'1h'` | `Cache-Control max-age` on `/media` |
| `inboundDbFile` | `INBOUND_DB_FILE` | `data/whatsapp.db` | SQLite database path |
| `inboundStoreLimit` | `INBOUND_STORE_LIMIT` | 500 | Max stored inbound messages (ring buffer) |
| `enableInboundSimulator` | `ENABLE_INBOUND_SIMULATOR` | true (non-production) | `/api/dev/inbound` toggle |
| `maxImageBytes` | `MAX_IMAGE_BYTES` | 5242880 | Image upload cap |
| `maxVideoBytes` | `MAX_VIDEO_BYTES` | 16777216 | Video upload cap |
| `maxTotalMediaBytes` | `MAX_TOTAL_MEDIA_BYTES` | 20971520 | Absolute media cap |
| `twilioConfigured` | (derived) | – | account SID valid + token + number present |

Also exports `describeMissingTwilioConfig()` — returns human-readable list of missing Twilio vars.

Non-positive/invalid numeric env values fall back to defaults (`toPositiveInteger`); booleans
accept `1/true/yes/on` (`toBoolean`); relative paths resolve against the project root.

### `src/config/constants.js` — code-level constants (not env-tunable)
```js
MULTER = { MAX_FILES: 1, MAX_FIELDS: 10, MAX_PARTS: 12, FILE_SIZE: config.maxVideoBytes }
MESSAGE = { MAX_TEXT_LENGTH: 1600, MAX_MEDIA_URL_LENGTH: 4096,
            SID_PATTERN: /^(SM|MM)[0-9a-fA-F]{32}$/, MAX_INBOUND_MEDIA: 10 }
HTTP = { JSON_BODY_LIMIT: '1mb', TRUST_PROXY_HOPS: 1, MEDIA_MAX_REDIRECTS: 3 }
```

### `src/config/twilio.js`
| Function | Parameters | Behavior |
|---|---|---|
| `getTwilioClient()` | – | Throws `503 TWILIO_NOT_CONFIGURED` (with missing-var list) when unconfigured; otherwise lazily creates and caches the Twilio REST client singleton. Also re-exports the `twilio` SDK for `validateRequest` use |
| `twilio` | – | Raw SDK reference |

---

## 9. App factory & server lifecycle

### `src/app.js` — `createApp()`
Returns a configured Express app (no listen):
1. `disable('x-powered-by')`; `trust proxy = HTTP.TRUST_PROXY_HOPS`
2. Parsers: `express.json({ limit: HTTP.JSON_BODY_LIMIT })`, `express.urlencoded({ extended: false })`
3. `/media` static route: inline header middleware (`nosniff` + `Content-Disposition` with sanitized basename) → `express.static(config.uploadDir, { index: false, dotfiles: 'ignore', fallthrough: true, maxAge: config.mediaCacheMaxAge })`
4. `GET /` → service name + health pointer
5. Routes (see §2), then `notFound`, then `errorHandler`

### `src/index.js` — entry point
1. `createApp()` → `app.listen(config.port)`
2. On listen: logs listening snapshot; `mediaService.startMediaCleanup()`; warns on missing Twilio config, missing/localhost `PUBLIC_BASE_URL`, and disabled signature validation
3. Graceful shutdown on `SIGINT`/`SIGTERM`: `server.close()` with a 10 s forced-exit fallback
4. Emits `ExperimentalWarning` from `node:sqlite` (expected on Node 22.x)

---

## 10. Testing

- `test/webhook.test.js` — inbound webhook: signature enforcement (valid/invalid/missing/disabled), storage + dedupe, media download (stubbed) and ignored types, simulator endpoint, SID validation; verifies actual SQLite persistence via a read-only connection; uses a temp `INBOUND_DB_FILE`
- `test/messages.test.js` — text/media/media-url endpoints with a stubbed Twilio client, validation errors, fetch endpoint, Twilio error mapping
- `test/media.test.js` — upload persistence + serving (content type, disposition), unsupported/oversized/missing file errors, media-url validation, `PUBLIC_BASE_URL` requirement, Twilio rejection mapping

Run: `npm test`.

---

## 11. Known limitations / deferred decisions

- Inbound messages use a JSON-`payload` SQLite design (ring buffer, `INBOUND_STORE_LIMIT`); a `user_version`-based migration framework is planned and will live in `src/db/connection.js`
- Media lives on local disk (`uploads/`); at multi-node scale, migrate to object storage (S3) behind the same `mediaService` interface
- SQLite is single-writer/single-node; a Postgres-backed `inboundStore` (same exported API) is the planned scaling path
- Logging is console-only (JSON lines); file-based log capture was considered but not implemented
