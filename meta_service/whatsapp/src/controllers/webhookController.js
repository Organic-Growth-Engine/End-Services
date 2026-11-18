'use strict';

const { recordInbound } = require('../services/inboundMessageService');
const { emptyTwimlResponse } = require('../utils/twiml');

async function handleInbound(req, res, next) {
  try {
    await recordInbound(req.body || {});

    res.status(200).type('text/xml').send(emptyTwimlResponse());
  } catch (err) {
    next(err);
  }
}

async function simulateInbound(req, res, next) {
  try {
    const message = await recordInbound(req.body || {});

    res.status(200).json({ message });
  } catch (err) {
    next(err);
  }
}

module.exports = {
  handleInbound,
  simulateInbound,
};
