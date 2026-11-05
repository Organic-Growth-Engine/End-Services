'use strict';

const mediaService = require('../services/mediaService');
const messageService = require('../services/messageService');
const { HttpError } = require('../utils/httpError');
const {
  optionalTextBody,
  requireMediaUrl,
  requireMessageSid,
  requireTextBody,
  requireWhatsAppAddress,
} = require('../utils/validation');

async function sendText(req, res, next) {
  try {
    const payload = req.body || {};
    const to = requireWhatsAppAddress(payload.to, 'to');
    const body = requireTextBody(payload.body, 'body');
    const message = await messageService.sendTextMessage({ to, body });

    res.status(201).json({ message });
  } catch (err) {
    next(err);
  }
}

async function sendMedia(req, res, next) {
  try {
    const payload = req.body || {};
    const to = requireWhatsAppAddress(payload.to, 'to');

    if (!req.file || !req.file.buffer) {
      throw new HttpError(
        400,
        'MEDIA_FILE_REQUIRED',
        'Attach a media file in the "file" form field.'
      );
    }

    const stored = await mediaService.saveUploadedMedia({ buffer: req.file.buffer });
    const body = optionalTextBody(payload.body, 'body');
    const message = await messageService.sendMediaMessage({
      to,
      body,
      mediaUrl: stored.localUrl,
    });

    res.status(201).json({
      message,
      media: {
        url: stored.localUrl,
        contentType: stored.contentType,
        kind: stored.kind,
        size: stored.size,
      },
    });
  } catch (err) {
    next(err);
  }
}

async function sendMediaUrl(req, res, next) {
  try {
    const payload = req.body || {};
    const to = requireWhatsAppAddress(payload.to, 'to');
    const mediaUrl = requireMediaUrl(payload.mediaUrl, 'mediaUrl');
    const body = optionalTextBody(payload.body, 'body');
    const message = await messageService.sendMediaMessage({ to, body, mediaUrl });

    res.status(201).json({ message });
  } catch (err) {
    next(err);
  }
}

async function getMessage(req, res, next) {
  try {
    const sid = requireMessageSid(req.params.sid);
    const message = await messageService.fetchMessage(sid);

    res.status(200).json({ message });
  } catch (err) {
    next(err);
  }
}

module.exports = {
  getMessage,
  sendMedia,
  sendMediaUrl,
  sendText,
};
