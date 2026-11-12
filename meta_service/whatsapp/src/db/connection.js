'use strict';

const fs = require('fs');
const fsPromises = require('fs/promises');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');

const { config } = require('../config/env');
const logger = require('../utils/logger');

const SCHEMA = `
CREATE TABLE IF NOT EXISTS inbound_messages (
  sid           TEXT PRIMARY KEY,
  received_at   TEXT NOT NULL,
  payload       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inbound_received_at
  ON inbound_messages (received_at DESC, sid DESC);
`;

let db = null;
let initPromise = null;

function openDatabase() {
  fs.mkdirSync(path.dirname(config.inboundDbFile), { recursive: true });

  const database = new DatabaseSync(config.inboundDbFile);
  database.exec('PRAGMA journal_mode = WAL;');
  database.exec(SCHEMA);

  return database;
}

async function migrateLegacyFile(database) {
  const legacyFile = path.join(
    path.dirname(config.inboundDbFile),
    'inbound-messages.json'
  );

  let rows;

  try {
    const raw = await fsPromises.readFile(legacyFile, 'utf8');
    const parsed = JSON.parse(raw);
    rows = Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    if (err.code !== 'ENOENT') {
      logger.warn('Could not read legacy inbound message file', {
        file: legacyFile,
        error: err.message,
      });
    }
    return;
  }

  if (rows.length > 0) {
    const upsert = database.prepare(`
      INSERT INTO inbound_messages (sid, received_at, payload)
      VALUES (?, ?, ?)
      ON CONFLICT(sid) DO UPDATE
      SET received_at = excluded.received_at,
          payload = excluded.payload
    `);

    for (const message of rows) {
      if (!message || typeof message.sid !== 'string' || !message.sid) {
        continue;
      }

      upsert.run(message.sid, message.receivedAt || '', JSON.stringify(message));
    }

    logger.info('Migrated legacy inbound message store into SQLite', {
      file: legacyFile,
      count: rows.length,
    });
  }

  await fsPromises
    .rename(legacyFile, `${legacyFile}.migrated`)
    .catch(() => {});
}

async function init() {
  if (!initPromise) {
    initPromise = (async () => {
      const database = openDatabase();
      await migrateLegacyFile(database);
      db = database;
    })().catch((err) => {
      initPromise = null;
      throw err;
    });
  }

  return initPromise;
}

async function ensureDb() {
  if (db) {
    return db;
  }

  await init();
  return db;
}

async function close() {
  const database = db;
  db = null;
  initPromise = null;

  if (database) {
    database.close();
  }
}

module.exports = {
  close,
  ensureDb,
};
