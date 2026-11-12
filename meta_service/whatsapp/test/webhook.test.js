'use strict';

const os = require('os');
const path = require('path');

process.env.NODE_ENV = 'test';
process.env.TWILIO_ACCOUNT_SID = `AC${'0'.repeat(32)}`;
process.env.TWILIO_AUTH_TOKEN = 'test-auth-token';
process.env.TWILIO_WHATSAPP_NUMBER = 'whatsapp:+14155238886';
process.env.PUBLIC_BASE_URL = 'http://localhost:3000';
process.env.TWILIO_VALIDATE_SIGNATURE = 'true';
process.env.ENABLE_INBOUND_SIMULATOR = 'true';
process.env.INBOUND_DB_FILE = path.join(os.tmpdir(), `wa-inbound-${process.pid}.db`);

const { after, beforeEach, test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs/promises');
const { DatabaseSync } = require('node:sqlite');
const request = require('supertest');

const { createApp } = require('../src/app');
const { config } = require('../src/config/env');
const { twilio } = require('../src/config/twilio');
const inboundStore = require('../src/db/inboundStore');
const mediaService = require('../src/services/mediaService');

const app = createApp();
const MESSAGE_SID = `SM${'b'.repeat(32)}`;
const FROM = 'whatsapp:+15551234567';
const TO = 'whatsapp:+14155238886';
const WEBHOOK_PATH = '/webhooks/twilio/inbound';

function stub(object, method, implementation) {
  const original = object[method];
  object[method] = implementation;

  return () => {
    object[method] = original;
  };
}

function sign(params) {
  return twilio.getExpectedTwilioSignature(
    config.authToken,
    `${config.publicBaseUrl}${WEBHOOK_PATH}`,
    params
  );
}

function postInbound(params, { signature } = {}) {
  const req = request(app).post(WEBHOOK_PATH).type('form');
  const value = signature === undefined ? sign(params) : signature;

  if (value) {
    req.set('X-Twilio-Signature', value);
  }

  return req.send(params);
}

function textPayload(overrides = {}) {
  return {
    MessageSid: MESSAGE_SID,
    From: FROM,
    To: TO,
    Body: 'Hello from WhatsApp',
    NumMedia: '0',
    ...overrides,
  };
}

beforeEach(async () => {
  await inboundStore.clear();
});

after(async () => {
  await inboundStore.clear();
  await inboundStore.close();
  await fs.rm(config.inboundDbFile, { force: true });
  await fs.rm(`${config.inboundDbFile}-wal`, { force: true });
  await fs.rm(`${config.inboundDbFile}-shm`, { force: true });
});

test('accepts a signed inbound text webhook, stores it, and returns empty TwiML', async () => {
  const response = await postInbound(textPayload());

  assert.equal(response.status, 200);
  assert.match(response.headers['content-type'], /text\/xml/);
  assert.match(response.text, /<Response><\/Response>/);

  const stored = await inboundStore.get(MESSAGE_SID);

  assert.ok(stored);
  assert.equal(stored.body, 'Hello from WhatsApp');
  assert.equal(stored.direction, 'inbound');
  assert.equal(stored.from, FROM);
  assert.deepEqual(stored.media, []);

  await inboundStore.flush();

  const db = new DatabaseSync(config.inboundDbFile, { readOnly: true });
  const row = db.prepare('SELECT sid FROM inbound_messages WHERE sid = ?').get(MESSAGE_SID);
  db.close();
  assert.ok(row);

  const list = await request(app).get('/api/inbound-messages');

  assert.equal(list.status, 200);
  assert.equal(list.body.messages.length, 1);
  assert.equal(list.body.messages[0].sid, MESSAGE_SID);

  const one = await request(app).get(`/api/inbound-messages/${MESSAGE_SID}`);

  assert.equal(one.status, 200);
  assert.equal(one.body.message.sid, MESSAGE_SID);
});

test('rejects a webhook with an invalid signature and stores nothing', async () => {
  const response = await postInbound(textPayload(), { signature: 'not-a-valid-signature' });

  assert.equal(response.status, 403);
  assert.equal(response.body.error.code, 'INVALID_TWILIO_SIGNATURE');
  assert.equal(await inboundStore.get(MESSAGE_SID), null);
});

test('rejects a signed webhook when the signature header is missing', async () => {
  const response = await postInbound(textPayload(), { signature: null });

  assert.equal(response.status, 403);
  assert.equal(response.body.error.code, 'INVALID_TWILIO_SIGNATURE');
});

test('skips signature validation when TWILIO_VALIDATE_SIGNATURE is false', async (t) => {
  const original = config.validateSignature;
  config.validateSignature = false;
  t.after(() => {
    config.validateSignature = original;
  });

  const response = await postInbound(textPayload(), { signature: null });

  assert.equal(response.status, 200);
  assert.ok(await inboundStore.get(MESSAGE_SID));
});

test('downloads allowed inbound media and stores the local URL', async (t) => {
  t.after(
    stub(mediaService, 'downloadInboundMedia', async (media) => ({
      ...media,
      localUrl: 'http://localhost:3000/media/abcdef0123456789.jpg',
      status: 'downloaded',
      size: 128,
    }))
  );

  const response = await postInbound(
    textPayload({
      Body: '',
      NumMedia: '1',
      MediaUrl0: `https://api.twilio.com/2010-04-01/Accounts/AC${'0'.repeat(
        32
      )}/Messages/${MESSAGE_SID}/Media/ME${'c'.repeat(32)}`,
      MediaContentType0: 'image/jpeg',
    })
  );

  assert.equal(response.status, 200);

  const stored = await inboundStore.get(MESSAGE_SID);

  assert.equal(stored.media.length, 1);
  assert.equal(stored.media[0].status, 'downloaded');
  assert.match(stored.media[0].localUrl, /\/media\/[0-9a-f]{16}\.jpg$/);
});

test('marks unsupported inbound media as ignored without downloading it', async (t) => {
  let downloads = 0;
  t.after(
    stub(mediaService, 'downloadInboundMedia', async (media) => {
      downloads += 1;
      return media;
    })
  );

  const response = await postInbound(
    textPayload({
      NumMedia: '1',
      MediaUrl0: 'https://example.com/document.pdf',
      MediaContentType0: 'application/pdf',
    })
  );

  assert.equal(response.status, 200);
  assert.equal(downloads, 0);

  const stored = await inboundStore.get(MESSAGE_SID);

  assert.equal(stored.media[0].status, 'ignored');
});

test('stores duplicate webhook deliveries only once', async () => {
  await postInbound(textPayload());
  await postInbound(textPayload());

  const list = await request(app).get('/api/inbound-messages');

  assert.equal(list.body.messages.length, 1);
  assert.equal(list.body.messages[0].sid, MESSAGE_SID);
});

test('rejects a webhook with an invalid MessageSid', async () => {
  const response = await postInbound(textPayload({ MessageSid: 'not-a-sid' }));

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_MESSAGE_SID');
});

test('the development simulator records an inbound message', async () => {
  const response = await request(app).post('/api/dev/inbound').send(textPayload());

  assert.equal(response.status, 200);
  assert.equal(response.body.message.sid, MESSAGE_SID);
  assert.ok(await inboundStore.get(MESSAGE_SID));
});
