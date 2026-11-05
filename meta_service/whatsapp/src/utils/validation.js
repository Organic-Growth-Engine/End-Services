'use strict';

const { HttpError } = require('./httpError');
const { parseWhatsAppAddress } = require('./phone');

const MAX_TEXT_LENGTH = 1600;
const MAX_MEDIA_URL_LENGTH = 4096;
const MESSAGE_SID_PATTERN = /^(SM|MM)[0-9a-fA-F]{32}$/;

function requireWhatsAppAddress(value, field) {
  const parsed = parseWhatsAppAddress(value);

  if (!parsed) {
    throw new HttpError(
      400,
      'INVALID_PHONE_NUMBER',
      `${field} must be an E.164 phone number, for example +15551234567 or whatsapp:+15551234567.`
    );
  }

  return parsed.whatsapp;
}

function requireTextBody(value, field) {
  if (typeof value !== 'string') {
    throw new HttpError(400, 'INVALID_BODY', `${field} is required and must be a string.`);
  }

  const body = value.trim();

  if (!body) {
    throw new HttpError(400, 'INVALID_BODY', `${field} must not be empty.`);
  }

  if (body.length > MAX_TEXT_LENGTH) {
    throw new HttpError(
      400,
      'INVALID_BODY',
      `${field} must be ${MAX_TEXT_LENGTH} characters or fewer.`
    );
  }

  return body;
}

function optionalTextBody(value, field) {
  if (value === undefined || value === null) {
    return undefined;
  }

  if (typeof value !== 'string') {
    throw new HttpError(400, 'INVALID_BODY', `${field} must be a string.`);
  }

  const body = value.trim();

  if (!body) {
    return undefined;
  }

  if (body.length > MAX_TEXT_LENGTH) {
    throw new HttpError(
      400,
      'INVALID_BODY',
      `${field} must be ${MAX_TEXT_LENGTH} characters or fewer.`
    );
  }

  return body;
}

function requireMediaUrl(value, field) {
  if (typeof value !== 'string') {
    throw new HttpError(400, 'INVALID_MEDIA_URL', `${field} is required and must be a URL.`);
  }

  const mediaUrl = value.trim();

  if (!mediaUrl || mediaUrl.length > MAX_MEDIA_URL_LENGTH) {
    throw new HttpError(
      400,
      'INVALID_MEDIA_URL',
      `${field} must be an http or https URL of ${MAX_MEDIA_URL_LENGTH} characters or fewer.`
    );
  }

  let parsed;

  try {
    parsed = new URL(mediaUrl);
  } catch (err) {
    parsed = null;
  }

  if (!parsed || (parsed.protocol !== 'http:' && parsed.protocol !== 'https:')) {
    throw new HttpError(400, 'INVALID_MEDIA_URL', `${field} must be an http or https URL.`);
  }

  return parsed.toString();
}

function requireMessageSid(value) {
  const sid = typeof value === 'string' ? value.trim() : '';

  if (!MESSAGE_SID_PATTERN.test(sid)) {
    throw new HttpError(
      400,
      'INVALID_MESSAGE_SID',
      'sid must be a Twilio message SID, for example SM followed by 32 hexadecimal characters.'
    );
  }

  return sid;
}

module.exports = {
  MAX_TEXT_LENGTH,
  optionalTextBody,
  requireMediaUrl,
  requireMessageSid,
  requireTextBody,
  requireWhatsAppAddress,
};
