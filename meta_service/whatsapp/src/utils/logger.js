'use strict';

function write(level, message, meta) {
  const entry = {
    time: new Date().toISOString(),
    level,
    message,
  };

  if (meta && typeof meta === 'object') {
    Object.assign(entry, meta);
  }

  const line = JSON.stringify(entry);

  if (level === 'error') {
    console.error(line);
  } else if (level === 'warn') {
    console.warn(line);
  } else {
    console.log(line);
  }
}

function info(message, meta) {
  write('info', message, meta);
}

function warn(message, meta) {
  write('warn', message, meta);
}

function error(message, meta) {
  write('error', message, meta);
}

module.exports = {
  info,
  warn,
  error,
};
