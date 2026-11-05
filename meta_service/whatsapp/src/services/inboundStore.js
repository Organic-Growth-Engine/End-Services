'use strict';

const fs = require('fs/promises');
const path = require('path');

const { config } = require('../config/env');
const logger = require('../utils/logger');

let messages = null;
let loadPromise = null;
let writeChain = Promise.resolve();

async function ensureLoaded() {
  if (messages) {
    return messages;
  }

  if (!loadPromise) {
    loadPromise = (async () => {
      await fs.mkdir(path.dirname(config.inboundStoreFile), { recursive: true });

      try {
        const raw = await fs.readFile(config.inboundStoreFile, 'utf8');
        const parsed = JSON.parse(raw);
        messages = Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        if (err.code !== 'ENOENT') {
          logger.warn('Could not read inbound message store', {
            file: config.inboundStoreFile,
            error: err.message,
          });
        }

        messages = [];
      }

      return messages;
    })();
  }

  return loadPromise;
}

function persist() {
  const snapshot = JSON.stringify(messages, null, 2);
  const file = config.inboundStoreFile;

  writeChain = writeChain
    .catch(() => {})
    .then(async () => {
      const temporaryFile = `${file}.tmp`;
      await fs.writeFile(temporaryFile, snapshot, 'utf8');
      await fs.rename(temporaryFile, file);
    })
    .catch((err) => {
      logger.error('Could not persist inbound message store', {
        file,
        error: err.message,
      });
    });

  return writeChain;
}

async function add(message) {
  const list = await ensureLoaded();
  const existingIndex = list.findIndex((item) => item.sid === message.sid);

  if (existingIndex >= 0) {
    list.splice(existingIndex, 1);
  }

  list.unshift(message);

  if (list.length > config.inboundStoreLimit) {
    list.length = config.inboundStoreLimit;
  }

  await persist();
  return message;
}

async function get(sid) {
  const list = await ensureLoaded();
  return list.find((item) => item.sid === sid) || null;
}

async function list({ limit = 50, before } = {}) {
  const list = await ensureLoaded();
  const safeLimit = Math.min(Math.max(Number.parseInt(limit, 10) || 50, 1), 100);
  const filtered = before
    ? list.filter((item) => (item.receivedAt || '') < before)
    : list;
  const page = filtered.slice(0, safeLimit);

  return {
    messages: page,
    nextCursor: filtered.length > safeLimit ? page[page.length - 1].receivedAt : null,
  };
}

async function clear() {
  const list = await ensureLoaded();
  list.length = 0;
  await persist();
}

async function flush() {
  await ensureLoaded();
  await writeChain;
}

module.exports = {
  add,
  clear,
  flush,
  get,
  list,
};
