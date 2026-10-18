// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { EventEmitter } from 'node:events';
import { randomUUID } from 'node:crypto';

export const PROTOCOL_VERSION = 'desktop-engine-1.0';
const EVENTS = new Set(['ui-ready', 'progress', 'versions', 'exit-requested', 'stopped', 'diagnostic', 'focus']);

export function checkedAppUrl(text) {
  const url = new URL(text);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port ||
      url.username || url.password || url.pathname !== '/' || url.search ||
      (url.hash && !/^#bootstrap=[A-Za-z0-9_-]{20,128}$/.test(url.hash))) {
    throw new Error('DESKTOP_URL_REJECTED');
  }
  return url;
}

export function allowAppNavigation(target, base) {
  try {
    const url = new URL(target), owned = checkedAppUrl(base);
    return url.origin === owned.origin && url.pathname === '/' && !url.username && !url.password && !url.search;
  } catch { return false; }
}

export class EngineChannel extends EventEmitter {
  constructor(child, { timeoutMs = 15000, maxLineBytes = 65536 } = {}) {
    super();
    this.child = child; this.timeoutMs = timeoutMs; this.maxLineBytes = maxLineBytes;
    this.pending = new Map(); this.buffer = Buffer.alloc(0); this.closed = false;
    child.stdout.on('data', data => this.receive(Buffer.from(data)));
    child.stdout.on('error', () => this.disconnect('ENGINE_READ_FAILED'));
    child.stdout.on('end', () => this.disconnect('ENGINE_STDOUT_EOF'));
    child.stdout.on('close', () => this.disconnect('ENGINE_STDOUT_CLOSED'));
    child.stdin.on('error', () => this.disconnect('ENGINE_WRITE_FAILED'));
    child.on('exit', (code, signal) => this.disconnect('ENGINE_EXIT', { code, signal }));
    child.on('error', () => this.disconnect('ENGINE_START_FAILED'));
  }
  receive(data) {
    if (this.closed) return;
    this.buffer = Buffer.concat([this.buffer, data]);
    let at;
    while ((at = this.buffer.indexOf(10)) !== -1) {
      const line = this.buffer.subarray(0, at); this.buffer = this.buffer.subarray(at + 1);
      if (line.length > this.maxLineBytes) return this.disconnect('ENGINE_LINE_LIMIT');
      let row;
      try { row = JSON.parse(line.toString('utf8')); }
      catch { return this.disconnect('ENGINE_PROTOCOL_INVALID'); }
      if (!row || typeof row !== 'object' || Array.isArray(row) || row.version !== PROTOCOL_VERSION)
        return this.disconnect('ENGINE_PROTOCOL_VERSION');
      if (typeof row.id === 'string') {
        const keys = Object.keys(row);
        const result = Object.hasOwn(row, 'result'), error = Object.hasOwn(row, 'error');
        if (result === error || keys.some(key => !['version', 'id', 'result', 'error'].includes(key)) ||
            error && (!row.error || typeof row.error !== 'object' || Array.isArray(row.error) ||
              Object.keys(row.error).some(key => key !== 'code') ||
              typeof row.error.code !== 'string' || !/^[A-Z][A-Z0-9_]{0,79}$/.test(row.error.code)))
          return this.disconnect('ENGINE_RESPONSE_INVALID');
        const request = this.pending.get(row.id);
        if (!request) continue; // Late response cannot complete another request.
        this.pending.delete(row.id); clearTimeout(request.timer);
        if (error) request.reject(new Error(row.error.code));
        else request.resolve(row.result);
      } else if (typeof row.event === 'string') {
        if (Object.keys(row).some(key => !['version', 'event', 'payload'].includes(key)))
          return this.disconnect('ENGINE_EVENT_INVALID');
        if (!EVENTS.has(row.event)) return this.disconnect('ENGINE_EVENT_REJECTED');
        // Bootstrap is private host data. Never expose it as a renderer log.
        if (row.event === 'ui-ready') {
          try { checkedAppUrl(row.payload?.url); }
          catch { return this.disconnect('ENGINE_URL_INVALID'); }
        }
        this.emit(row.event, row.payload);
      } else return this.disconnect('ENGINE_PROTOCOL_INVALID');
    }
    if (this.buffer.length > this.maxLineBytes) this.disconnect('ENGINE_LINE_LIMIT');
  }
  request(method, params = {}) {
    if (!['initialize', 'focus', 'versions', 'request-exit'].includes(method))
      return Promise.reject(new Error('ENGINE_METHOD_REJECTED'));
    if (this.closed) return Promise.reject(new Error('ENGINE_DISCONNECTED'));
    if (this.pending.size >= 32) return Promise.reject(new Error('ENGINE_REQUESTS_BUSY'));
    const id = randomUUID();
    let line;
    try { line = JSON.stringify({ version: PROTOCOL_VERSION, id, method, params }) + '\n'; }
    catch { return Promise.reject(new Error('ENGINE_PARAMS_INVALID')); }
    if (Buffer.byteLength(line) > this.maxLineBytes) return Promise.reject(new Error('ENGINE_LINE_LIMIT'));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id); reject(new Error('ENGINE_REQUEST_TIMEOUT'));
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      const failed = error => {
        if (!error) return;
        const request = this.pending.get(id);
        if (request) { clearTimeout(request.timer); this.pending.delete(id); request.reject(new Error('ENGINE_WRITE_FAILED')); }
      };
      try { this.child.stdin.write(line, failed); }
      catch (error) { failed(error); }
    });
  }
  disconnect(code, details = {}) {
    if (this.closed) return;
    this.closed = true; this.buffer = Buffer.alloc(0);
    for (const row of this.pending.values()) { clearTimeout(row.timer); row.reject(new Error(code)); }
    this.pending.clear(); this.emit('disconnected', { code, ...details });
  }
}
