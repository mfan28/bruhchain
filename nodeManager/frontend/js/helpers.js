export const API = '/api/v1';

// ─── DOM ───
export function $(id) { return document.getElementById(id); }

export function show(el, html) { el.style.display = 'block'; el.innerHTML = html; }
export function hide(el) { el.style.display = 'none'; }
export function setEl(id, val) { const el = $(id); if (el) el.textContent = val; }
export function styleEl(id, prop, val) { const el = $(id); if (el) el.style[prop] = val; }

export function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ─── JSON highlight ───
export function jsonHighlight(obj) {
  const json = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
  return json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"([^"]+)":/g, '<span class="key">"$1"</span>:')
    .replace(/: "([^"]+)"/g, ': <span class="string">"$1"</span>')
    .replace(/: (\d+)/g, ': <span class="number">$1</span>')
    .replace(/: (true|false)/g, ': <span class="bool">$1</span>')
    .replace(/: (null)/g, ': <span class="null">$1</span>');
}

// ─── API ───
export async function apiGet(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// ─── Formatting ───
export function formatTimeAgo(timestamp, now) {
  if (!timestamp) return '—';
  if (!now) now = Math.floor(Date.now() / 1000);
  const diff = now - timestamp;
  if (diff < 5) return 'just now';
  if (diff < 60) return diff + 's ago';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

export function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ─── Misc ───
export function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

export async function sha256(data) {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(data);
  const hashBuffer = await crypto.subtle.digest('SHA-256', bytes);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}