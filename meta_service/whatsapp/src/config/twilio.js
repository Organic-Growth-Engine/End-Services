'use strict';

const twilio = require('twilio');
const { config, describeMissingTwilioConfig } = require('./env');
const { HttpError } = require('../utils/httpError');

let client;

function getTwilioClient() {
  if (!config.twilioConfigured) {
    throw new HttpError(
      503,
      'TWILIO_NOT_CONFIGURED',
      `Twilio is not configured. Missing: ${describeMissingTwilioConfig().join(', ')}`
    );
  }

  if (!client) {
    client = twilio(config.accountSid, config.authToken);
  }

  return client;
}

module.exports = {
  getTwilioClient,
  twilio,
};
