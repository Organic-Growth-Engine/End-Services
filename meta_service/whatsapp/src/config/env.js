'use strict';

const path = require('path');
const { parseWhatsAppAddress } = require('../utils/phone');

require('dotenv').config({
  path: path.resolve(__dirname, '../../.env'),
  quiet: true,
});

function toBoolean(value, fallback) {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }

  return ['1', 'true', 'yes', 'on'].includes(String(value).trim().toLowerCase());
}

function toPositiveInteger(value, fallback) {
  const parsed = Number.parseInt(value, 10);

  if (!Number.isInteger(parsed) || parsed <= 0) {
    return fallback;
  }

  return parsed;
}

function trim(value) {
  return typeof value === 'string' ? value.trim() : '';
}

const PROJECT_ROOT = path.resolve(__dirname, '../../');

function resolvePath(value, fallback) {
  const candidate = trim(value) || fallback;
  return path.isAbsolute(candidate) ? candidate : path.resolve(PROJECT_ROOT, candidate);
}

const accountSid = trim(process.env.TWILIO_ACCOUNT_SID);
const authToken = trim(process.env.TWILIO_AUTH_TOKEN);
const whatsappNumberRaw = trim(process.env.TWILIO_WHATSAPP_NUMBER);
const whatsappAddress = parseWhatsAppAddress(whatsappNumberRaw);
const accountSidValid = /^AC[0-9a-fA-F]{32}$/.test(accountSid);

const config = {
  port: toPositiveInteger(process.env.PORT, 3000),
  publicBaseUrl: trim(process.env.PUBLIC_BASE_URL).replace(/\/+$/, ''),
  accountSid,
  authToken,
  whatsappNumber: whatsappAddress ? whatsappAddress.whatsapp : whatsappNumberRaw,
  whatsappNumberValid: Boolean(whatsappAddress),
  accountSidValid,
  validateSignature: toBoolean(process.env.TWILIO_VALIDATE_SIGNATURE, true),
  uploadTtlMinutes: toPositiveInteger(process.env.UPLOAD_TTL_MINUTES, 60),
  uploadDir: resolvePath(process.env.MEDIA_UPLOAD_DIR, 'uploads'),
  mediaCleanupIntervalMs: toPositiveInteger(
    process.env.MEDIA_CLEANUP_INTERVAL_MS,
    5 * 60 * 1000
  ),
  mediaDownloadTimeoutMs: toPositiveInteger(process.env.MEDIA_DOWNLOAD_TIMEOUT_MS, 10000),
  mediaCacheMaxAge: trim(process.env.MEDIA_CACHE_MAX_AGE) || '1h',
  inboundDbFile: resolvePath(process.env.INBOUND_DB_FILE, 'data/whatsapp.db'),
  inboundStoreLimit: toPositiveInteger(process.env.INBOUND_STORE_LIMIT, 500),
  enableInboundSimulator: toBoolean(
    process.env.ENABLE_INBOUND_SIMULATOR,
    process.env.NODE_ENV !== 'production'
  ),
  maxImageBytes: toPositiveInteger(process.env.MAX_IMAGE_BYTES, 5 * 1024 * 1024),
  maxVideoBytes: toPositiveInteger(process.env.MAX_VIDEO_BYTES, 16 * 1024 * 1024),
  maxTotalMediaBytes: toPositiveInteger(process.env.MAX_TOTAL_MEDIA_BYTES, 20 * 1024 * 1024),
  twilioConfigured: Boolean(accountSidValid && authToken && whatsappAddress),
};

function describeMissingTwilioConfig() {
  const missing = [];

  if (!config.accountSid) {
    missing.push('TWILIO_ACCOUNT_SID');
  } else if (!config.accountSidValid) {
    missing.push('TWILIO_ACCOUNT_SID (must start with AC followed by 32 hexadecimal characters)');
  }

  if (!config.authToken) {
    missing.push('TWILIO_AUTH_TOKEN');
  }

  if (!whatsappNumberRaw) {
    missing.push('TWILIO_WHATSAPP_NUMBER');
  } else if (!config.whatsappNumberValid) {
    missing.push('TWILIO_WHATSAPP_NUMBER (must be E.164, for example whatsapp:+14155238886)');
  }

  return missing;
}

module.exports = {
  config,
  describeMissingTwilioConfig,
};
