'use strict';

process.env.TWILIO_ACCOUNT_SID = `AC${'0'.repeat(32)}`;
process.env.TWILIO_AUTH_TOKEN = 'test-auth-token';
process.env.TWILIO_WHATSAPP_NUMBER = 'whatsapp:+14155238886';
process.env.PUBLIC_BASE_URL = 'http://localhost:3000';
process.env.TWILIO_VALIDATE_SIGNATURE = 'true';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const request = require('supertest');

const { createApp } = require('../src/app');
const { config } = require('../src/config/env');
const twilioConfig = require('../src/config/twilio');
const messageService = require('../src/services/messageService');

const app = createApp();
const MESSAGE_SID = `SM${'a'.repeat(32)}`;

const SERIALIZED_MESSAGE = {
  sid: MESSAGE_SID,
  status: 'queued',
  direction: 'outbound-api',
  to: 'whatsapp:+15551234567',
  from: 'whatsapp:+14155238886',
  body: 'Hello',
  numSegments: '1',
  numMedia: '0',
  mediaUrls: [],
  dateCreated: '2026-01-01T00:00:00.000Z',
  dateUpdated: null,
  errorCode: null,
  errorMessage: null,
};

const TWILIO_MESSAGE = {
  ...SERIALIZED_MESSAGE,
  dateCreated: new Date('2026-01-01T00:00:00.000Z'),
};

function stub(object, method, implementation) {
  const original = object[method];
  object[method] = implementation;

  return () => {
    object[method] = original;
  };
}

test('GET /health reports configuration without secrets', async () => {
  const response = await request(app).get('/health');

  assert.equal(response.status, 200);
  assert.equal(response.body.status, 'ok');
  assert.equal(response.body.twilioConfigured, true);
  assert.equal(response.body.signatureValidationEnabled, true);
  assert.equal(typeof response.body.uptimeSeconds, 'number');
  assert.equal(typeof response.body.timestamp, 'string');
  assert.equal(JSON.stringify(response.body).includes('test-auth-token'), false);
});

test('POST /api/messages/text sends a canonical WhatsApp address and trimmed body', async (t) => {
  const calls = [];
  t.after(stub(messageService, 'sendTextMessage', async (payload) => {
    calls.push(payload);
    return SERIALIZED_MESSAGE;
  }));

  const response = await request(app)
    .post('/api/messages/text')
    .send({ to: '+1 (555) 123-4567', body: '  Hello  ' });

  assert.equal(response.status, 201);
  assert.deepEqual(calls, [
    { to: 'whatsapp:+15551234567', body: 'Hello' },
  ]);
  assert.deepEqual(response.body.message, SERIALIZED_MESSAGE);
});

test('POST /api/messages/text accepts an already-prefixed whatsapp address', async (t) => {
  const calls = [];
  t.after(stub(messageService, 'sendTextMessage', async (payload) => {
    calls.push(payload);
    return SERIALIZED_MESSAGE;
  }));

  const response = await request(app)
    .post('/api/messages/text')
    .send({ to: 'whatsapp:+15551234567', body: 'Hello' });

  assert.equal(response.status, 201);
  assert.deepEqual(calls, [
    { to: 'whatsapp:+15551234567', body: 'Hello' },
  ]);
});

test('POST /api/messages/text returns a serialized message with a mocked Twilio client', async (t) => {
  let received;
  t.after(stub(twilioConfig, 'getTwilioClient', () => ({
    messages: {
      create: async (payload) => {
        received = payload;
        return TWILIO_MESSAGE;
      },
    },
  })));

  const response = await request(app)
    .post('/api/messages/text')
    .send({ to: '+15551234567', body: 'Hello' });

  assert.equal(response.status, 201);
  assert.deepEqual(received, {
    from: config.whatsappNumber,
    to: 'whatsapp:+15551234567',
    body: 'Hello',
  });
  assert.deepEqual(response.body.message, SERIALIZED_MESSAGE);
});

test('POST /api/messages/text rejects a missing body without calling Twilio', async (t) => {
  let called = false;
  t.after(stub(messageService, 'sendTextMessage', async () => {
    called = true;
    return SERIALIZED_MESSAGE;
  }));

  const response = await request(app)
    .post('/api/messages/text')
    .send({ to: '+15551234567' });

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_BODY');
  assert.equal(called, false);
});

test('POST /api/messages/text returns a clean error for invalid JSON', async () => {
  const response = await request(app)
    .post('/api/messages/text')
    .set('Content-Type', 'application/json')
    .send('{"to":');

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_JSON');
  assert.equal(response.body.error.message, 'Request body must be valid JSON.');
});

test('POST /api/messages/text rejects an invalid phone number without calling Twilio', async (t) => {
  let called = false;
  t.after(stub(messageService, 'sendTextMessage', async () => {
    called = true;
    return SERIALIZED_MESSAGE;
  }));

  const response = await request(app)
    .post('/api/messages/text')
    .send({ to: 'not-a-phone-number', body: 'Hello' });

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_PHONE_NUMBER');
  assert.equal(called, false);
});

test('POST /api/messages/text rejects text longer than 1600 characters', async (t) => {
  let called = false;
  t.after(stub(messageService, 'sendTextMessage', async () => {
    called = true;
    return SERIALIZED_MESSAGE;
  }));

  const response = await request(app)
    .post('/api/messages/text')
    .send({ to: '+15551234567', body: 'a'.repeat(1601) });

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_BODY');
  assert.equal(called, false);
});

test('GET /api/messages/:sid returns a message', async (t) => {
  const requestedSids = [];
  t.after(stub(messageService, 'fetchMessage', async (sid) => {
    requestedSids.push(sid);
    return SERIALIZED_MESSAGE;
  }));

  const response = await request(app).get(`/api/messages/${MESSAGE_SID}`);

  assert.equal(response.status, 200);
  assert.deepEqual(requestedSids, [MESSAGE_SID]);
  assert.deepEqual(response.body.message, SERIALIZED_MESSAGE);
});

test('GET /api/messages/:sid rejects an invalid SID without calling Twilio', async (t) => {
  let called = false;
  t.after(stub(messageService, 'fetchMessage', async () => {
    called = true;
    return SERIALIZED_MESSAGE;
  }));

  const response = await request(app).get('/api/messages/SM123');

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'INVALID_MESSAGE_SID');
  assert.equal(called, false);
});

test('sendTextMessage sends the configured from number and serializes the response', async (t) => {
  let received;
  t.after(stub(twilioConfig, 'getTwilioClient', () => ({
    messages: {
      create: async (payload) => {
        received = payload;
        return TWILIO_MESSAGE;
      },
    },
  })));

  const message = await messageService.sendTextMessage({
    to: 'whatsapp:+15551234567',
    body: 'Hello',
  });

  assert.deepEqual(received, {
    from: config.whatsappNumber,
    to: 'whatsapp:+15551234567',
    body: 'Hello',
  });
  assert.deepEqual(message, SERIALIZED_MESSAGE);
});

test('sendTextMessage maps Twilio rejections to a safe 400 response', async (t) => {
  const twilioError = Object.assign(new Error('The To number is invalid.'), {
    status: 400,
    code: 21211,
    moreInfo: 'https://www.twilio.com/docs/errors/21211',
  });

  t.after(stub(twilioConfig, 'getTwilioClient', () => ({
    messages: {
      create: async () => {
        throw twilioError;
      },
    },
  })));

  await assert.rejects(
    () => messageService.sendTextMessage({ to: 'whatsapp:+15551234567', body: 'Hello' }),
    (err) => {
      assert.equal(err.statusCode, 400);
      assert.equal(err.code, 'TWILIO_REJECTED');
      assert.deepEqual(err.details, {
        twilioCode: 21211,
        twilioStatus: 400,
        twilioMessage: 'The To number is invalid.',
        moreInfo: 'https://www.twilio.com/docs/errors/21211',
      });
      return true;
    }
  );
});

test('sendTextMessage hides credential failures behind a 502 response', async (t) => {
  const twilioError = Object.assign(new Error('Authentication Error'), {
    status: 401,
    code: 20003,
  });

  t.after(stub(twilioConfig, 'getTwilioClient', () => ({
    messages: {
      create: async () => {
        throw twilioError;
      },
    },
  })));

  await assert.rejects(
    () => messageService.sendTextMessage({ to: 'whatsapp:+15551234567', body: 'Hello' }),
    (err) => {
      assert.equal(err.statusCode, 502);
      assert.equal(err.code, 'TWILIO_AUTH_FAILED');
      assert.equal(err.details, undefined);
      return true;
    }
  );
});

test('sendTextMessage maps network failures to a 502 response', async (t) => {
  const networkError = Object.assign(new Error('socket hang up'), {
    code: 'ECONNRESET',
  });

  t.after(stub(twilioConfig, 'getTwilioClient', () => ({
    messages: {
      create: async () => {
        throw networkError;
      },
    },
  })));

  await assert.rejects(
    () => messageService.sendTextMessage({ to: 'whatsapp:+15551234567', body: 'Hello' }),
    (err) => {
      assert.equal(err.statusCode, 502);
      assert.equal(err.code, 'TWILIO_UNAVAILABLE');
      return true;
    }
  );
});

test('fetchMessage requests the SID from Twilio and serializes the response', async (t) => {
  let requestedSid;
  const messages = (sid) => ({
    fetch: async () => {
      requestedSid = sid;
      return TWILIO_MESSAGE;
    },
  });

  t.after(stub(twilioConfig, 'getTwilioClient', () => ({ messages })));

  const message = await messageService.fetchMessage(MESSAGE_SID);

  assert.equal(requestedSid, MESSAGE_SID);
  assert.deepEqual(message, SERIALIZED_MESSAGE);
});
