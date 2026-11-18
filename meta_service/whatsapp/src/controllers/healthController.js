'use strict';

const { config } = require('../config/env');

function getHealth(req, res) {
  res.status(200).json({
    status: 'ok',
    uptimeSeconds: Math.round(process.uptime()),
    twilioConfigured: config.twilioConfigured,
    signatureValidationEnabled: config.validateSignature,
    publicBaseUrlConfigured: Boolean(config.publicBaseUrl),
    inboundSimulatorEnabled: config.enableInboundSimulator,
    timestamp: new Date().toISOString(),
  });
}

module.exports = { getHealth };
