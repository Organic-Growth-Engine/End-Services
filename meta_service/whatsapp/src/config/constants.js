'use strict';

const { config } = require('./env');

const MULTER = {
  MAX_FILES: 1,
  MAX_FIELDS: 10,
  MAX_PARTS: 12,
  FILE_SIZE: config.maxVideoBytes,
};

const MESSAGE = {
  MAX_TEXT_LENGTH: 1600,
  MAX_MEDIA_URL_LENGTH: 4096,
  SID_PATTERN: /^(SM|MM)[0-9a-fA-F]{32}$/,
  MAX_INBOUND_MEDIA: 10,
};

const HTTP = {
  JSON_BODY_LIMIT: '1mb',
  TRUST_PROXY_HOPS: 1,
  MEDIA_MAX_REDIRECTS: 3,
};

module.exports = { MULTER, MESSAGE, HTTP };
