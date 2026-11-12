'use strict';

const { HttpError } = require('../utils/httpError');
const { isAllowedMimeType } = require('../utils/media');
const { MESSAGE } = require('../config/constants');
const inboundStore = require('../db/inboundStore');
const mediaService = require('./mediaService');

const { SID_PATTERN: MESSAGE_SID_PATTERN, MAX_INBOUND_MEDIA } = MESSAGE;

function parseInboundPayload(payload) {
  const source = payload || {};
  const sid =
    typeof source.MessageSid === 'string'
      ? source.MessageSid.trim()
      : typeof source.SmsMessageSid === 'string'
        ? source.SmsMessageSid.trim()
        : '';

  if (!MESSAGE_SID_PATTERN.test(sid)) {
    throw new HttpError(
      400,
      'INVALID_MESSAGE_SID',
      'MessageSid must be a Twilio message SID, for example SM followed by 32 hexadecimal characters.'
    );
  }

  const parsedNumMedia = Number.parseInt(source.NumMedia, 10);
  const numMedia =
    Number.isInteger(parsedNumMedia) && parsedNumMedia > 0
      ? Math.min(parsedNumMedia, MAX_INBOUND_MEDIA)
      : 0;

  const media = [];

  for (let index = 0; index < numMedia; index += 1) {
    const url = source[`MediaUrl${index}`];

    if (!url) {
      continue;
    }

    const contentType = source[`MediaContentType${index}`] || null;
    media.push({
      url,
      contentType,
      localUrl: null,
      status: isAllowedMimeType(contentType) ? 'pending' : 'ignored',
    });
  }

  return {
    sid,
    direction: 'inbound',
    status: source.MessageStatus || source.SmsStatus || 'received',
    from: source.From || null,
    to: source.To || null,
    body: typeof source.Body === 'string' ? source.Body : '',
    profileName: source.ProfileName || null,
    waId: source.WaId || null,
    externalUserId: source.ExternalUserId || null,
    username: source.Username || null,
    numSegments: source.NumSegments || null,
    numMedia: String(numMedia),
    media,
    receivedAt: new Date().toISOString(),
  };
}

async function resolveMedia(message) {
  if (message.media.length === 0) {
    return message;
  }

  const existing = await inboundStore.get(message.sid);
  const alreadyDownloaded = new Map();

  if (existing && Array.isArray(existing.media)) {
    existing.media.forEach((item) => {
      if (item.status === 'downloaded' && item.url) {
        alreadyDownloaded.set(item.url, item);
      }
    });
  }

  const resolved = [];

  for (const item of message.media) {
    if (alreadyDownloaded.has(item.url)) {
      resolved.push(alreadyDownloaded.get(item.url));
      continue;
    }

    if (item.status === 'ignored') {
      resolved.push(item);
      continue;
    }

    resolved.push(await mediaService.downloadInboundMedia(item));
  }

  return { ...message, media: resolved };
}

async function recordInbound(payload) {
  const parsed = parseInboundPayload(payload);
  const message = await resolveMedia(parsed);

  return inboundStore.add(message);
}

module.exports = {
  parseInboundPayload,
  recordInbound,
};
