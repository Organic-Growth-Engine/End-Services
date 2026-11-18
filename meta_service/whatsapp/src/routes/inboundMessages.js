'use strict';

const express = require('express');

const {
  getInbound,
  listInbound,
} = require('../controllers/inboundMessageController');

const router = express.Router();

router.get('/', listInbound);
router.get('/:sid', getInbound);

module.exports = router;
