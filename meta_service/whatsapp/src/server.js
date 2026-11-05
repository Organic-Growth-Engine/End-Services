'use strict';

const { createApp } = require('./app');
const { config } = require('./config/env');
const mediaService = require('./services/mediaService');
const logger = require('./utils/logger');

const app = createApp();
const localBaseUrlPattern = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::|\/|$)/i;

const server = app.listen(config.port, () => {
  logger.info('Server listening', {
    port: config.port,
    twilioConfigured: config.twilioConfigured,
    signatureValidationEnabled: config.validateSignature,
    inboundSimulatorEnabled: config.enableInboundSimulator,
  });

  mediaService.startMediaCleanup();

  if (!config.twilioConfigured) {
    logger.warn('Twilio is not configured. Message endpoints will return 503 until .env is completed.');
  }

  if (!config.publicBaseUrl) {
    logger.warn('PUBLIC_BASE_URL is empty. Webhooks and Twilio media fetching will not work.');
  } else if (localBaseUrlPattern.test(config.publicBaseUrl)) {
    logger.warn(
      'PUBLIC_BASE_URL points to localhost. Twilio cannot fetch local media or deliver webhooks. Use your ngrok HTTPS URL.'
    );
  }

  if (!config.validateSignature) {
    logger.warn('Twilio webhook signature validation is DISABLED. Do not use this setting in production.');
  }
});

function shutdown(signal) {
  logger.info('Shutting down', { signal });

  server.close(() => {
    process.exit(0);
  });

  setTimeout(() => process.exit(1), 10000).unref();
}

['SIGINT', 'SIGTERM'].forEach((signal) => {
  process.on(signal, () => shutdown(signal));
});

module.exports = { server };
