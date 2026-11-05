'use strict';

const twilioConfig = require('../config/twilio');
const { config } = require('../config/env');
const { HttpError } = require('../utils/httpError');

function toIsoString(value) {
  if (!value) {
    return null;
  }

  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function serializeMessage(message) {
  const source = message && typeof message === 'object' ? message : {};

  return {
    sid: source.sid ?? null,
    status: source.status ?? null,
    direction: source.direction ?? null,
    to: source.to ?? null,
    from: source.from ?? null,
    body: source.body ?? null,
    numSegments: source.numSegments ?? null,
    numMedia: source.numMedia ?? null,
    mediaUrls: Array.isArray(source.mediaUrls) ? source.mediaUrls : [],
    dateCreated: toIsoString(source.dateCreated),
    dateUpdated: toIsoString(source.dateUpdated),
    errorCode: source.errorCode ?? null,
    errorMessage: source.errorMessage ?? null,
  };
}

function mapTwilioError(err) {
  if (err instanceof HttpError) {
    return err;
  }

  const status = Number(err && err.status);

  if (status === 404) {
    return new HttpError(404, 'TWILIO_RESOURCE_NOT_FOUND', 'Twilio could not find the requested message.');
  }

  if (status === 401 || status === 403) {
    return new HttpError(
      502,
      'TWILIO_AUTH_FAILED',
      'Twilio rejected the credentials. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.'
    );
  }

  if (status === 429) {
    return new HttpError(429, 'TWILIO_RATE_LIMITED', 'Twilio rate limit reached. Try again later.');
  }

  if (status >= 400 && status < 500) {
    return new HttpError(400, 'TWILIO_REJECTED', 'Twilio rejected the request.', {
      twilioCode: err.code ?? null,
      twilioStatus: status,
      twilioMessage: err.message ?? null,
      moreInfo: err.moreInfo ?? null,
    });
  }

  return new HttpError(502, 'TWILIO_UNAVAILABLE', 'Could not reach Twilio. Try again.');
}

async function sendTextMessage({ to, body }) {
  const client = twilioConfig.getTwilioClient();

  try {
    const message = await client.messages.create({
      from: config.whatsappNumber,
      to,
      body,
    });

    return serializeMessage(message);
  } catch (err) {
    throw mapTwilioError(err);
  }
}

async function sendMediaMessage({ to, body, mediaUrl }) {
  const client = twilioConfig.getTwilioClient();
  const payload = {
    from: config.whatsappNumber,
    to,
    mediaUrl: [mediaUrl],
  };

  if (body) {
    payload.body = body;
  }

  try {
    const message = await client.messages.create(payload);

    return {
      ...serializeMessage(message),
      mediaUrls: [mediaUrl],
    };
  } catch (err) {
    throw mapTwilioError(err);
  }
}

async function fetchMessage(sid) {
  const client = twilioConfig.getTwilioClient();

  try {
    const message = await client.messages(sid).fetch();
    return serializeMessage(message);
  } catch (err) {
    throw mapTwilioError(err);
  }
}

module.exports = {
  fetchMessage,
  mapTwilioError,
  sendMediaMessage,
  sendTextMessage,
  serializeMessage,
};
