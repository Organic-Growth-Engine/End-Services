'use strict';

const { HttpError } = require('../utils/httpError');
const logger = require('../utils/logger');

function describeBodyParserError(err) {
  if (err.type === 'entity.parse.failed') {
    return {
      statusCode: 400,
      code: 'INVALID_JSON',
      message: 'Request body must be valid JSON.',
    };
  }

  if (err.type === 'entity.too.large') {
    return {
      statusCode: 413,
      code: 'PAYLOAD_TOO_LARGE',
      message: 'Request body is too large.',
    };
  }

  return null;
}

function describeMulterError(err) {
  if (!err || err.name !== 'MulterError') {
    return null;
  }

  if (err.code === 'LIMIT_FILE_SIZE') {
    return {
      statusCode: 413,
      code: 'FILE_TOO_LARGE',
      message: 'Media exceeds the maximum allowed size.',
    };
  }

  if (err.code === 'LIMIT_UNEXPECTED_FILE') {
    return {
      statusCode: 400,
      code: 'UNEXPECTED_FILE',
      message: 'Upload the media file in the "file" form field.',
    };
  }

  if (err.code === 'LIMIT_FILE_COUNT') {
    return {
      statusCode: 400,
      code: 'TOO_MANY_FILES',
      message: 'Only one media file is allowed per message.',
    };
  }

  return {
    statusCode: 400,
    code: 'INVALID_MULTIPART',
    message: 'The multipart request could not be processed.',
  };
}

function errorHandler(err, req, res, next) {
  if (res.headersSent) {
    return next(err);
  }

  const clientError = describeBodyParserError(err) || describeMulterError(err);
  const statusCode = clientError
    ? clientError.statusCode
    : err.statusCode || err.status || 500;
  const code = clientError
    ? clientError.code
    : err.code || 'INTERNAL_ERROR';
  const message = clientError
    ? clientError.message
    : err instanceof HttpError || statusCode < 500
      ? err.message
      : 'Internal server error';

  if (statusCode >= 500) {
    logger.error('Unhandled request error', {
      method: req.method,
      path: req.originalUrl,
      error: err.message,
      stack: process.env.NODE_ENV === 'production' ? undefined : err.stack,
    });
  } else {
    logger.warn('Request rejected', {
      method: req.method,
      path: req.originalUrl,
      statusCode,
      code,
      message,
    });
  }

  const body = {
    error: {
      code,
      message,
    },
  };

  if (err.details !== undefined) {
    body.error.details = err.details;
  }

  res.status(statusCode).json(body);
}

module.exports = { errorHandler };
