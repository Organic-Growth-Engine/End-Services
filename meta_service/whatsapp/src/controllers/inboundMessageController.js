'use strict';

const inboundStore = require('../services/inboundStore');
const { HttpError } = require('../utils/httpError');
const { requireMessageSid } = require('../utils/validation');

async function listInbound(req, res, next) {
  try {
    const parsedLimit = Number.parseInt(req.query.limit, 10);
    const before = typeof req.query.before === 'string' ? req.query.before : undefined;
    const result = await inboundStore.list({
      limit: Number.isInteger(parsedLimit) ? parsedLimit : 50,
      before,
    });

    res.status(200).json(result);
  } catch (err) {
    next(err);
  }
}

async function getInbound(req, res, next) {
  try {
    const sid = requireMessageSid(req.params.sid);
    const message = await inboundStore.get(sid);

    if (!message) {
      throw new HttpError(
        404,
        'INBOUND_MESSAGE_NOT_FOUND',
        'No stored inbound message with that SID.'
      );
    }

    res.status(200).json({ message });
  } catch (err) {
    next(err);
  }
}

module.exports = {
  getInbound,
  listInbound,
};
