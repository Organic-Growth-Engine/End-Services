'use strict';

const fs = require('fs/promises');
const path = require('path');
const axios = require('axios');

const { config } = require('../config/env');
const { HTTP } = require('../config/constants');
const { HttpError } = require('../utils/httpError');
const logger = require('../utils/logger');
const {
  createMediaFilename,
  detectMediaType,
  isSafeRemoteMediaUrl,
  isTwilioMediaUrl,
  mediaKind,
} = require('../utils/media');

async function ensureUploadDir() {
  await fs.mkdir(config.uploadDir, { recursive: true });
}

function buildPublicMediaUrl(filename) {
  if (!config.publicBaseUrl) {
    return null;
  }

  return `${config.publicBaseUrl}/media/${filename}`;
}

function requirePublicMediaUrl(filename) {
  const url = buildPublicMediaUrl(filename);

  if (!url) {
    throw new HttpError(
      503,
      'PUBLIC_BASE_URL_NOT_CONFIGURED',
      'PUBLIC_BASE_URL must be a public URL (for example your ngrok HTTPS URL) before sending locally stored media.'
    );
  }

  return url;
}

function maxBytesFor(kind) {
  return kind === 'image' ? config.maxImageBytes : config.maxVideoBytes;
}

async function persistMediaBuffer(buffer, { requirePublicUrl = false } = {}) {
  const contentType = detectMediaType(buffer);

  if (!contentType) {
    throw new HttpError(
      400,
      'INVALID_MEDIA_TYPE',
      'Media must be a JPEG or PNG image or an MP4 video.'
    );
  }

  const kind = mediaKind(contentType);
  const maxBytes = maxBytesFor(kind);

  if (buffer.length > maxBytes) {
    throw new HttpError(413, 'MEDIA_TOO_LARGE', `${kind} media must be ${maxBytes} bytes or fewer.`, {
      kind,
      size: buffer.length,
      maxBytes,
    });
  }

  if (buffer.length > config.maxTotalMediaBytes) {
    throw new HttpError(
      413,
      'MEDIA_TOO_LARGE',
      `Media must be ${config.maxTotalMediaBytes} bytes or fewer.`,
      { size: buffer.length, maxBytes: config.maxTotalMediaBytes }
    );
  }

  const filename = createMediaFilename(contentType);
  const localUrl = requirePublicUrl
    ? requirePublicMediaUrl(filename)
    : buildPublicMediaUrl(filename);

  await ensureUploadDir();
  await fs.writeFile(path.join(config.uploadDir, filename), buffer);

  return {
    filename,
    contentType,
    kind,
    size: buffer.length,
    localUrl,
  };
}

async function saveUploadedMedia({ buffer }) {
  return persistMediaBuffer(buffer, { requirePublicUrl: true });
}

async function downloadInboundMedia(media) {
  const url = media && media.url;
  const declaredContentType = media && media.contentType;

  if (!url) {
    return { ...media, localUrl: null, status: 'failed', error: 'Missing MediaUrl.' };
  }

  if (!isSafeRemoteMediaUrl(url)) {
    return { ...media, localUrl: null, status: 'failed', error: 'Media URL is not allowed.' };
  }

  if (!config.twilioConfigured) {
    return {
      ...media,
      localUrl: null,
      status: 'failed',
      error: 'Twilio credentials are not configured.',
    };
  }

  const request = {
    responseType: 'arraybuffer',
    timeout: config.mediaDownloadTimeoutMs,
    maxContentLength: config.maxVideoBytes,
    maxBodyLength: config.maxVideoBytes,
    maxRedirects: HTTP.MEDIA_MAX_REDIRECTS,
    headers: { Accept: '*/*' },
  };

  if (isTwilioMediaUrl(url)) {
    request.auth = {
      username: config.accountSid,
      password: config.authToken,
    };
  }

  try {
    const response = await axios.get(url, request);
    const stored = await persistMediaBuffer(Buffer.from(response.data));

    return {
      url,
      contentType: stored.contentType,
      declaredContentType,
      localUrl: stored.localUrl,
      status: 'downloaded',
      size: stored.size,
    };
  } catch (err) {
    logger.warn('Inbound media download failed', {
      url,
      error: err.message,
    });

    return {
      url,
      contentType: declaredContentType,
      localUrl: null,
      status: 'failed',
      error: err.message,
    };
  }
}

async function cleanupExpiredMedia() {
  await ensureUploadDir();

  const cutoff = Date.now() - config.uploadTtlMinutes * 60 * 1000;
  const entries = await fs.readdir(config.uploadDir, { withFileTypes: true });
  let removed = 0;

  for (const entry of entries) {
    if (!entry.isFile() || entry.name === '.gitkeep') {
      continue;
    }

    const filePath = path.join(config.uploadDir, entry.name);

    try {
      const stats = await fs.stat(filePath);

      if (stats.mtimeMs < cutoff) {
        await fs.unlink(filePath);
        removed += 1;
      }
    } catch (err) {
      logger.warn('Could not clean up media file', { file: entry.name, error: err.message });
    }
  }

  return removed;
}

function startMediaCleanup() {
  cleanupExpiredMedia().catch((err) => {
    logger.warn('Initial media cleanup failed', { error: err.message });
  });

  const timer = setInterval(() => {
    cleanupExpiredMedia().catch((err) => {
      logger.warn('Media cleanup failed', { error: err.message });
    });
  }, config.mediaCleanupIntervalMs);

  timer.unref();
  return timer;
}

module.exports = {
  buildPublicMediaUrl,
  cleanupExpiredMedia,
  downloadInboundMedia,
  requirePublicMediaUrl,
  saveUploadedMedia,
  startMediaCleanup,
};
