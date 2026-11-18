'use strict';

const { ensureDb, close } = require('./connection');
const { config } = require('../config/env');
const logger = require('../utils/logger');

const UPSERT = `
INSERT INTO inbound_messages (sid, received_at, payload)
VALUES (?, ?, ?)
ON CONFLICT(sid) DO UPDATE
SET received_at = excluded.received_at,
    payload = excluded.payload
`;

const TRIM = `
DELETE FROM inbound_messages
WHERE sid NOT IN (
  SELECT sid FROM inbound_messages
  ORDER BY received_at DESC, sid DESC
  LIMIT ?
)
`;

const SELECT_ALL_COLUMNS = 'sid, received_at, payload';

function rowToMessage(row) {
  if (!row) {
    return null;
  }

  try {
    return JSON.parse(row.payload);
  } catch (err) {
    logger.error('Could not parse stored inbound message', {
      sid: row.sid,
      error: err.message,
    });
    return null;
  }
}

async function add(message) {
  const database = await ensureDb();

  database
    .prepare(UPSERT)
    .run(message.sid, message.receivedAt || '', JSON.stringify(message));

  database.prepare(TRIM).run(config.inboundStoreLimit);

  return message;
}

async function get(sid) {
  const database = await ensureDb();
  const row = database
    .prepare(`SELECT ${SELECT_ALL_COLUMNS} FROM inbound_messages WHERE sid = ?`)
    .get(sid);

  return rowToMessage(row);
}

async function list({ limit = 50, before } = {}) {
  const database = await ensureDb();
  const safeLimit = Math.min(Math.max(Number.parseInt(limit, 10) || 50, 1), 100);

  const rows = before
    ? database
        .prepare(
          `SELECT ${SELECT_ALL_COLUMNS} FROM inbound_messages
           WHERE received_at < ?
           ORDER BY received_at DESC, sid DESC
           LIMIT ?`
        )
        .all(before, safeLimit + 1)
    : database
        .prepare(
          `SELECT ${SELECT_ALL_COLUMNS} FROM inbound_messages
           ORDER BY received_at DESC, sid DESC
           LIMIT ?`
        )
        .all(safeLimit + 1);

  const hasMore = rows.length > safeLimit;
  const page = hasMore ? rows.slice(0, safeLimit) : rows;

  return {
    messages: page.map(rowToMessage),
    nextCursor: hasMore ? page[page.length - 1].receivedAt : null,
  };
}

async function clear() {
  const database = await ensureDb();
  database.exec('DELETE FROM inbound_messages;');
}

async function flush() {
  await ensureDb();
}

module.exports = {
  add,
  clear,
  close,
  flush,
  get,
  list,
};
