'use strict';

const { HttpError } = require('../utils/httpError');

function notFound(req, res, next) {
  next(new HttpError(404, 'NOT_FOUND', `Route not found: ${req.method} ${req.originalUrl}`));
}

module.exports = { notFound };
