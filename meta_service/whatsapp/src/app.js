'use strict';

const path = require('path');
const express = require('express');

const routes = require('./routes');
const { notFound } = require('./middleware/notFound');
const { errorHandler } = require('./middleware/errorHandler');
const { UPLOAD_DIR } = require('./services/mediaService');

function createApp() {
  const app = express();

  app.disable('x-powered-by');
  app.set('trust proxy', 1);

  app.use(express.json({ limit: '1mb' }));
  app.use(express.urlencoded({ extended: false }));

  app.use(
    '/media',
    (req, res, next) => {
      const filename = path.basename(req.path);

      res.setHeader('X-Content-Type-Options', 'nosniff');
      res.setHeader('Content-Disposition', `inline; filename="${filename}"`);
      next();
    },
    express.static(UPLOAD_DIR, {
      index: false,
      dotfiles: 'ignore',
      fallthrough: true,
      maxAge: '1h',
    })
  );

  app.get('/', (req, res) => {
    res.status(200).json({
      name: 'twilio-whatsapp-integration',
      health: '/health',
    });
  });

  app.use(routes);
  app.use(notFound);
  app.use(errorHandler);

  return app;
}

module.exports = { createApp };
