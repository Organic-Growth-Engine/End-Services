'use strict';

const express = require('express');
const multer = require('multer');

const { config } = require('../config/env');
const {
  getMessage,
  sendMedia,
  sendMediaUrl,
  sendText,
} = require('../controllers/messageController');

const router = express.Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: config.maxVideoBytes,
    files: 1,
    fields: 10,
    parts: 12,
  },
});

router.post('/text', sendText);
router.post('/media', upload.single('file'), sendMedia);
router.post('/media-url', sendMediaUrl);
router.get('/:sid', getMessage);

module.exports = router;
