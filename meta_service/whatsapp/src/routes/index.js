'use strict';

const express = require('express');

const { config } = require('../config/env');
const { getHealth } = require('../controllers/healthController');
const { simulateInbound } = require('../controllers/webhookController');
const inboundMessagesRouter = require('./inboundMessages');
const messagesRouter = require('./messages');
const webhooksRouter = require('./webhooks');

const router = express.Router();

router.get('/health', getHealth);
router.use('/webhooks/twilio', webhooksRouter);
router.use('/api/inbound-messages', inboundMessagesRouter);
router.use('/api/messages', messagesRouter);

if (config.enableInboundSimulator) {
  router.post('/api/dev/inbound', simulateInbound);
}

module.exports = router;
