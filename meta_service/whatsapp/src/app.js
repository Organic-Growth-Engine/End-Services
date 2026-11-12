'use strict';

const path = require('path');
const express = require('express');

const routes = require('./routes');
const { notFound } = require('./middleware/notFound');
const { errorHandler } = require('./middleware/errorHandler');
const { config } = require('./config/env');
const { HTTP } = require('./config/constants');

function createApp() {
  const app = express();

  app.disable('x-powered-by');
  app.set('trust proxy', HTTP.TRUST_PROXY_HOPS);

  app.use(express.json({ limit: HTTP.JSON_BODY_LIMIT }));
  app.use(express.urlencoded({ extended: false }));

  app.use(
    '/media',
    (req, res, next) => {
      const filename = path.basename(req.path);

      res.setHeader('X-Content-Type-Options', 'nosniff');
      res.setHeader('Content-Disposition', `inline; filename="${filename}"`);
      next();
    },
    express.static(config.uploadDir, {
      index: false,
      dotfiles: 'ignore',
      fallthrough: true,
      maxAge: config.mediaCacheMaxAge,
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
