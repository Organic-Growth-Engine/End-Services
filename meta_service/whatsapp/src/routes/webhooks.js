'use strict';

const express = require('express');

const { handleInbound } = require('../controllers/webhookController');
const { requireTwilioSignature } = require('../middleware/twilioSignature');

const router = express.Router();


/**
 * Express middleware that validates the X-Twilio-Signature header.
 * Terminates every branch via next() and never writes a response;
 * the TwiML response is produced by the route handler that follows.
 * Passes through without validating when TWILIO_VALIDATE_SIGNATURE=false.
 */
router.post('/inbound', requireTwilioSignature, handleInbound);

module.exports = router;
