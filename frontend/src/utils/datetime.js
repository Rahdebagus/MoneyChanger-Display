// ─── Date & Time Formatting ───────────────────────────────────────────────────
//
// The API sends UTC. Everything here renders in the branch timezone (Asia/
// Makassar by default for Bali) so a time shown on screen is the time staff
// would read off a clock on the wall.

const DISPLAY_TIMEZONE = import.meta.env?.VITE_DISPLAY_TIMEZONE || "Asia/Makassar";

/** The API returns naive UTC strings; mark them as UTC before parsing. */
function parse(value) {
  if (!value) return null;
  if (value instanceof Date) return value;

  const text = String(value);
  const normalised =
    /[zZ]$|[+-]\d{2}:?\d{2}$/.test(text) ? text : `${text}Z`;

  const parsed = new Date(normalised);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDateTime(value, { timeZone = DISPLAY_TIMEZONE } = {}) {
  const date = parse(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(date);
}

export function formatDate(value, { timeZone = DISPLAY_TIMEZONE } = {}) {
  const date = parse(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeZone }).format(date);
}

export function formatTime(value, { timeZone = DISPLAY_TIMEZONE } = {}) {
  const date = parse(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("id-ID", { timeStyle: "short", timeZone }).format(date);
}

export function relativeTime(value) {
  const date = parse(value);
  if (!date) return "—";

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 0) {
    const ahead = Math.abs(seconds);
    if (ahead < 60) return "sebentar lagi";
    if (ahead < 3600) return `dalam ${Math.round(ahead / 60)} menit`;
    if (ahead < 86400) return `dalam ${Math.round(ahead / 3600)} jam`;
    return `dalam ${Math.round(ahead / 86400)} hari`;
  }

  if (seconds < 45) return "baru saja";
  if (seconds < 3600) return `${Math.round(seconds / 60)} menit lalu`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} jam lalu`;
  if (seconds < 2592000) return `${Math.round(seconds / 86400)} hari lalu`;
  return formatDate(value);
}

export const displayTimezone = DISPLAY_TIMEZONE;
