/**
 * Shared formatting helpers.
 *
 * The most important one is date handling: SQLite writes naive UTC strings
 * ("2026-09-06 13:00:00"), and `new Date()` parses a string without an offset
 * as *local* time, so every timestamp in the UI used to be shifted by the
 * viewer's UTC offset. `parseUtc` treats an offset-less value as UTC.
 */

const OFFSET_PATTERN = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/** Parse an API timestamp into a Date, treating offset-less values as UTC. */
export function parseUtc(value) {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;

  let text = String(value).trim();
  if (!text) return null;

  // "YYYY-MM-DD HH:MM:SS" is valid SQLite but not valid ISO-8601.
  if (text.includes(' ') && !text.includes('T')) text = text.replace(' ', 'T');
  if (!OFFSET_PATTERN.test(text)) text += 'Z';

  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/** Full date and time in the viewer's locale, or a dash. */
export function formatDateTime(value, fallback = '—') {
  const date = parseUtc(value);
  return date ? date.toLocaleString() : fallback;
}

/** Date only, in the viewer's locale. */
export function formatDate(value, fallback = '—') {
  const date = parseUtc(value);
  return date ? date.toLocaleDateString() : fallback;
}

const RELATIVE_UNITS = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
  ['second', 1],
];

/** "3 minutes ago" / "in 2 hours". Falls back to the absolute time on failure. */
export function formatRelative(value, fallback = '—') {
  const date = parseUtc(value);
  if (!date) return fallback;

  const seconds = (date.getTime() - Date.now()) / 1000;
  const absolute = Math.abs(seconds);
  if (absolute < 45) return seconds < 0 ? 'just now' : 'in a moment';

  for (const [unit, size] of RELATIVE_UNITS) {
    if (absolute >= size || unit === 'second') {
      const amount = Math.round(seconds / size);
      try {
        return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(amount, unit);
      } catch {
        return date.toLocaleString();
      }
    }
  }
  return date.toLocaleString();
}

/** Human-readable byte size. */
export function formatBytes(bytes, fallback = '—') {
  if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return fallback;
  const value = Number(bytes);
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
}

/** Seconds as a compact duration, e.g. "1m 04s". */
export function formatDuration(seconds, fallback = '—') {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return fallback;
  const total = Number(seconds);
  if (total < 1) return `${total.toFixed(2)}s`;
  if (total < 60) return `${total.toFixed(1)}s`;
  const minutes = Math.floor(total / 60);
  const rest = Math.round(total % 60);
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, '0')}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`;
}

/** Seconds as an interval a human configured, e.g. "5 min". */
export function formatInterval(seconds, fallback = '—') {
  if (seconds === null || seconds === undefined) return fallback;
  const value = Number(seconds);
  if (Number.isNaN(value)) return fallback;
  if (value < 60) return `${value}s`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  if (value < 86400) return `${(value / 3600).toFixed(value % 3600 ? 1 : 0)} h`;
  return `${(value / 86400).toFixed(value % 86400 ? 1 : 0)} d`;
}

/** Shorten a long path from the left, keeping the filename visible. */
export function truncatePath(path, maxLength = 60) {
  if (!path) return '';
  return path.length > maxLength ? `…${path.slice(-maxLength)}` : path;
}

/** Title-case a machine value like "in_progress" for display. */
export function humanize(value) {
  if (!value) return '';
  return String(value).replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
