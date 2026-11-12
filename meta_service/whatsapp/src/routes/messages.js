'use strict';

const express = require('express');
const multer = require('multer');

const { MULTER } = require('../config/constants');
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
    fileSize: MULTER.FILE_SIZE,
    files: MULTER.MAX_FILES,
    fields: MULTER.MAX_FIELDS,
    parts: MULTER.MAX_PARTS,
  },
});

router.post('/text', sendText);
router.post('/media', upload.single('file'), sendMedia);
router.post('/media-url', sendMediaUrl);
router.get('/:sid', getMessage);

module.exports = router;
