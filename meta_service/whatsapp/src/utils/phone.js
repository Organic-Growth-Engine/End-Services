'use strict';

const E164_PATTERN = /^\+[1-9]\d{6,14}$/;

function parseWhatsAppAddress(value) {
  if (typeof value !== 'string') {
    return null;
  }

  let candidate = value.trim();

  if (!candidate) {
    return null;
  }

  if (/^whatsapp:/i.test(candidate)) {
    candidate = candidate.slice('whatsapp:'.length);
  }

  candidate = candidate.replace(/[\s().-]/g, '');

  if (!E164_PATTERN.test(candidate)) {
    return null;
  }

  return {
    e164: candidate,
    whatsapp: `whatsapp:${candidate}`,
  };
}

module.exports = { parseWhatsAppAddress };
