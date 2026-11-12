'use strict';

const crypto = require('crypto');

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

const MIME_TO_EXTENSION = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'video/mp4': 'mp4',
};

const KIND_BY_MIME = {
  'image/jpeg': 'image',
  'image/png': 'image',
  'video/mp4': 'video',
};

function normalizeMimeType(value) {
  if (typeof value !== 'string') {
    return null;
  }

  const mimeType = value.split(';')[0].trim().toLowerCase();

  if (!mimeType) {
    return null;
  }

  return mimeType === 'image/jpg' ? 'image/jpeg' : mimeType;
}

function isAllowedMimeType(value) {
  return Boolean(KIND_BY_MIME[normalizeMimeType(value)]);
}

function mediaKind(value) {
  return KIND_BY_MIME[normalizeMimeType(value)] || null;
}

function extensionForMime(value) {
  return MIME_TO_EXTENSION[normalizeMimeType(value)] || null;
}

function createMediaFilename(mimeType) {
  const extension = extensionForMime(mimeType);

  if (!extension) {
    throw new Error(`Unsupported media type: ${mimeType}`);
  }

  return `${crypto.randomBytes(8).toString('hex')}.${extension}`;
}

function detectMediaType(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 12) {
    return null;
  }

  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) {
    return 'image/jpeg';
  }

  if (buffer.subarray(0, 8).equals(PNG_SIGNATURE)) {
    return 'image/png';
  }

  if (buffer.subarray(4, 8).toString('latin1') === 'ftyp') {
    return 'video/mp4';
  }

  return null;
}

function isTwilioMediaUrl(value) {
  try {
    const url = new URL(value);

    if (url.protocol !== 'https:') {
      return false;
    }

    return (
      url.hostname === 'api.twilio.com' ||
      url.hostname === 'media.twiliocdn.com' ||
      url.hostname.endsWith('.twilio.com')
    );
  } catch (err) {
    return false;
  }
}

function isSafeRemoteMediaUrl(value) {
  try {
    const url = new URL(value);

    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return false;
    }

    const hostname = url.hostname.toLowerCase();

    if (
      hostname === 'localhost' ||
      hostname === '0.0.0.0' ||
      hostname === '[::1]' ||
      hostname === '::1' ||
      hostname.endsWith('.local') ||
      hostname.endsWith('.internal') ||
      hostname.startsWith('127.') ||
      hostname.startsWith('10.') ||
      hostname.startsWith('192.168.') ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(hostname)
    ) {
      return false;
    }

    return true;
  } catch (err) {
    return false;
  }
}

module.exports = {
  createMediaFilename,
  detectMediaType,
  extensionForMime,
  isAllowedMimeType,
  isSafeRemoteMediaUrl,
  isTwilioMediaUrl,
  mediaKind,
  normalizeMimeType,
};
