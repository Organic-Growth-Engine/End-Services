'use strict';

const { config } = require('../config/env');
const { twilio } = require('../config/twilio');
const { HttpError } = require('../utils/httpError');

function requireTwilioSignature(req, res, next) {
  if (!config.validateSignature) {
    return next();
  }

  if (!config.twilioConfigured) {
    return next(
      new HttpError(
        503,
        'TWILIO_NOT_CONFIGURED',
        'Twilio credentials are required to validate webhook signatures.'
      )
    );
  }

  if (!config.publicBaseUrl) {
    return next(
      new HttpError(
        503,
        'PUBLIC_BASE_URL_NOT_CONFIGURED',
        'PUBLIC_BASE_URL is required to validate webhook signatures.'
      )
    );
  }

  const signature = req.get('X-Twilio-Signature');

  if (!signature) {
    return next(
      new HttpError(403, 'INVALID_TWILIO_SIGNATURE', 'Missing X-Twilio-Signature header.')
    );
  }

  const url = `${config.publicBaseUrl}${req.originalUrl}`;

  try {
    const valid = twilio.validateRequest(
      config.authToken,
      signature,
      url,
      req.body || {}
    );

    if (!valid) {
      return next(
        new HttpError(403, 'INVALID_TWILIO_SIGNATURE', 'The Twilio signature is invalid.')
      );
    }
  } catch (err) {
    return next(
      new HttpError(
        403,
        'INVALID_TWILIO_SIGNATURE',
        'The Twilio signature could not be validated.'
      )
    );
  }

  return next();
}

module.exports = { requireTwilioSignature };
