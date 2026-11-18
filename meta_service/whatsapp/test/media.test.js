'use strict';

const os = require('os');
const path = require('path');

process.env.NODE_ENV = 'test';
process.env.TWILIO_ACCOUNT_SID = `AC${'0'.repeat(32)}`;
process.env.TWILIO_AUTH_TOKEN = 'test-auth-token';
process.env.TWILIO_WHATSAPP_NUMBER = 'whatsapp:+14155238886';
process.env.PUBLIC_BASE_URL = 'http://localhost:3000';
process.env.TWILIO_VALIDATE_SIGNATURE = 'true';
process.env.INBOUND_DB_FILE = path.join(os.tmpdir(), `wa-media-${process.pid}.db`);

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs/promises');
const request = require('supertest');

const { createApp } = require('../src/app');
const { config } = require('../src/config/env');
const twilioConfig = require('../src/config/twilio');
const mediaService = require('../src/services/mediaService');

const app = createApp();
const MESSAGE_SID = `SM${'a'.repeat(32)}`;
const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(64, 0x11)]);
const MP4 = Buffer.concat([
  Buffer.from([0x00, 0x00, 0x00, 0x18]),
  Buffer.from('ftypisom'),
  Buffer.alloc(64, 0x22),
]);

const TWILIO_MESSAGE = {
  sid: MESSAGE_SID,
  status: 'queued',
  direction: 'outbound-api',
  to: 'whatsapp:+15551234567',
  from: 'whatsapp:+14155238886',
  body: null,
  numSegments: '1',
  numMedia: '1',
  dateCreated: new Date('2026-01-01T00:00:00.000Z'),
  dateUpdated: null,
  errorCode: null,
  errorMessage: null,
};

function stub(object, method, implementation) {
  const original = object[method];
  object[method] = implementation;

  return () => {
    object[method] = original;
  };
}

async function uploadNames() {
  try {
    return new Set(await fs.readdir(config.uploadDir));
  } catch (err) {
    return new Set();
  }
}

async function removeNewUploads(before) {
  const after = await uploadNames();
  const created = [...after].filter((name) => !before.has(name) && name !== '.gitkeep');

  await Promise.all(
    created.map((name) =>
      fs.unlink(path.join(config.uploadDir, name)).catch(() => {})
    )
  );
}

function stubTwilio(t) {
  let received;
  t.after(
    stub(twilioConfig, 'getTwilioClient', () => ({
      messages: {
        create: async (payload) => {
          received = payload;
          return TWILIO_MESSAGE;
        },
      },
    }))
  );

  return () => received;
}

test('POST /api/messages/media stores and sends a JPEG with a caption', async (t) => {
  const before = await uploadNames();
  t.after(() => removeNewUploads(before));
  const received = stubTwilio(t);

  const response = await request(app)
    .post('/api/messages/media')
    .field('to', '+1 (555) 123-4567')
    .field('body', '  Caption  ')
    .attach('file', JPEG, { filename: 'photo.jpg', contentType: 'image/jpeg' });

  assert.equal(response.status, 201);
  assert.equal(received().from, config.whatsappNumber);
  assert.equal(received().to, 'whatsapp:+15551234567');
  assert.equal(received().body, 'Caption');
  assert.match(
    received().mediaUrl[0],
    /^http:\/\/localhost:3000\/media\/[0-9a-f]{16}\.jpg$/
  );
  assert.deepEqual(response.body.message.mediaUrls, received().mediaUrl);
  assert.equal(response.body.media.contentType, 'image/jpeg');
  assert.equal(response.body.media.kind, 'image');

  const served = await request(app).get(new URL(received().mediaUrl[0]).pathname);

  assert.equal(served.status, 200);
  assert.equal(served.headers['content-type'], 'image/jpeg');
  assert.match(
    served.headers['content-disposition'],
    /^inline; filename="[0-9a-f]{16}\.jpg"$/
  );
});

test('POST /api/messages/media forwards a caption for MP4 video', async (t) => {
  const before = await uploadNames();
  t.after(() => removeNewUploads(before));
  const received = stubTwilio(t);

  const response = await request(app)
    .post('/api/messages/media')
    .field('to', '+15551234567')
    .field('body', '  Video caption  ')
    .attach('file', MP4, { filename: 'clip.mp4', contentType: 'video/mp4' });

  assert.equal(response.status, 201);
  assert.equal(received().body, 'Video caption');
  assert.match(received().mediaUrl[0], /\.mp4$/);
  assert.equal(response.body.media.kind, 'video');
});

test('POST /api/messages/media-url forwards a caption for hosted video media', async (t) => {
  const received = stubTwilio(t);

  const response = await request(app)
    .post('/api/messages/media-url')
    .send({
      to: '+1 (555) 123-4567',
      mediaUrl: 'https://example.com/clip.mp4',
      body: '  Video caption  ',
    });

  assert.equal(response.status, 201);
  assert.deepEqual(received(), {
    from: config.whatsappNumber,
    to: 'whatsapp:+15551234567',
    mediaUrl: ['https://example.com/clip.mp4'],
    body: 'Video caption',
  });
  assert.deepEqual(response.body.message.mediaUrls, ['https://example.com/clip.mp4']);
});

test('POST /api/messages/media rejects unsupported media without writing a file', async (t) => {
  const before = await uploadNames();
  t.after(() => removeNewUploads(before));

  const response = await request(app)
    .post('/api/messages/media')
    .field('to', '+15551234567')
    .attach('file', Buffer.from('%PDF-1.4'), {
      filename: 'document.pdf',
      contentType: 'application/pdf',
    });

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_MEDIA_TYPE');
  assert.equal((await uploadNames()).size, before.size);
});

test('POST /api/messages/media rejects images over the image size limit', async (t) => {
  const before = await uploadNames();
  t.after(() => removeNewUploads(before));
  const oversized = Buffer.concat([
    Buffer.from([0xff, 0xd8, 0xff, 0xe0]),
    Buffer.alloc(config.maxImageBytes, 0x33),
  ]);

  const response = await request(app)
    .post('/api/messages/media')
    .field('to', '+15551234567')
    .attach('file', oversized, { filename: 'large.jpg', contentType: 'image/jpeg' });

  assert.equal(response.status, 413);
  assert.equal(response.body.error.code, 'MEDIA_TOO_LARGE');
});

test('POST /api/messages/media returns a clean error for oversized multipart uploads', async () => {
  const oversized = Buffer.concat([
    Buffer.from([0x00, 0x00, 0x00, 0x18]),
    Buffer.from('ftypisom'),
    Buffer.alloc(config.maxVideoBytes, 0x44),
  ]);

  const response = await request(app)
    .post('/api/messages/media')
    .field('to', '+15551234567')
    .attach('file', oversized, { filename: 'huge.mp4', contentType: 'video/mp4' });

  assert.equal(response.status, 413);
  assert.equal(response.body.error.code, 'FILE_TOO_LARGE');
});

test('POST /api/messages/media requires a file', async () => {
  const response = await request(app)
    .post('/api/messages/media')
    .field('to', '+15551234567');

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'MEDIA_FILE_REQUIRED');
});

test('POST /api/messages/media-url sends hosted media and trims the caption', async (t) => {
  const received = stubTwilio(t);

  const response = await request(app)
    .post('/api/messages/media-url')
    .send({
      to: '+1 (555) 123-4567',
      mediaUrl: 'https://example.com/image.png',
      body: '  Caption  ',
    });

  assert.equal(response.status, 201);
  assert.deepEqual(received(), {
    from: config.whatsappNumber,
    to: 'whatsapp:+15551234567',
    mediaUrl: ['https://example.com/image.png'],
    body: 'Caption',
  });
  assert.deepEqual(response.body.message.mediaUrls, ['https://example.com/image.png']);
});

test('POST /api/messages/media-url rejects non-http media URLs', async () => {
  const response = await request(app)
    .post('/api/messages/media-url')
    .send({ to: '+15551234567', mediaUrl: 'ftp://example.com/image.png' });

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_MEDIA_URL');
});

test('POST /api/messages/media requires PUBLIC_BASE_URL before storing media', async (t) => {
  const before = await uploadNames();
  const original = config.publicBaseUrl;
  config.publicBaseUrl = '';
  t.after(() => {
    config.publicBaseUrl = original;
    return removeNewUploads(before);
  });

  const response = await request(app)
    .post('/api/messages/media')
    .field('to', '+15551234567')
    .attach('file', JPEG, { filename: 'photo.jpg', contentType: 'image/jpeg' });

  assert.equal(response.status, 503);
  assert.equal(response.body.error.code, 'PUBLIC_BASE_URL_NOT_CONFIGURED');
  assert.equal((await uploadNames()).size, before.size);
});

test('POST /api/messages/media-url maps Twilio rejections to a safe error', async (t) => {
  t.after(
    stub(twilioConfig, 'getTwilioClient', () => ({
      messages: {
        create: async () => {
          throw Object.assign(new Error('Media is not accessible.'), {
            status: 400,
            code: 21620,
          });
        },
      },
    }))
  );

  const response = await request(app)
    .post('/api/messages/media-url')
    .send({ to: '+15551234567', mediaUrl: 'https://example.com/image.png' });

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'TWILIO_REJECTED');
});
