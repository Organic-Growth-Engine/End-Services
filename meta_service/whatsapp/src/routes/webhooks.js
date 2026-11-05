'use strict';

const express = require('express');

const { handleInbound } = require('../controllers/webhookController');
const { requireTwilioSignature } = require('../middleware/twilioSignature');

const router = express.Router();

router.post('/inbound', requireTwilioSignature, handleInbound);

module.exports = router;
