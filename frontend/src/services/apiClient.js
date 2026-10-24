// ─── Central API Client ───────────────────────────────────────────────────────
//
// Every network call in the app goes through here so that auth headers, error
// shapes and the base URL live in exactly one place.
//
// The base URL comes from VITE_API_BASE_URL at build time. It falls back to the
// current origin's host on port 8000, which keeps a phone or a TV on the same
// LAN working without a rebuild — hardcoding "localhost" would break every
// device except the developer's own machine.

const DEFAULT_PORT = "8000";

function resolveBaseUrl() {
  const configured = import.meta.env?.VITE_API_BASE_URL;
  if (configured) return configured.replace(/\/$/, "");

  if (typeof window !== "undefined" && window.location) {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:${DEFAULT_PORT}`;
  }
  return `http://localhost:${DEFAULT_PORT}`;
}

export const API_BASE = resolveBaseUrl();

export const TOKEN_STORAGE_KEY = "pam.auth.token";
export const DEVICE_TOKEN_KEY = "pam.device.token";

// ─── Error type ───────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(message, { status, requestId, body } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
    this.body = body;
  }

  // What a user should actually see: the server's message plus a traceable id.
  get displayMessage() {
    if (this.requestId) return `${this.message} (ID: ${this.requestId})`;
    return this.message;
  }
}

// ─── Token storage ────────────────────────────────────────────────────────────
// Wrapped because storage throws in private mode and in some kiosk browsers.

export function readStored(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key, value) {
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable; the session simply does not survive a reload */
  }
}

let onUnauthorized = null;
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// ─── Core request ─────────────────────────────────────────────────────────────

async function parseBody(response) {
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  return null;
}

export async function request(path, options = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, options.timeoutMs ?? 30000);
  if (options.signal?.aborted) controller.abort();
  else options.signal?.addEventListener("abort", abort, { once: true });
  try {
    return await sendRequest(path, { ...options, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new ApiError("Server terlalu lama merespons. Silakan coba lagi.", { status: 0 });
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

async function sendRequest(path, options) {
  const {
    method = "GET",
    body,
    token,
    tokenKey = TOKEN_STORAGE_KEY,
    raw = false,
    blob = false,
    signal,
    headers: extraHeaders = {},
    skipAuthRedirect = false,
  } = options;

  const headers = { ...extraHeaders };
  const authToken = token !== undefined ? token : readStored(tokenKey);
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let payload = body;
  if (body !== undefined && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: payload,
      signal,
    });
  } catch (networkError) {
    if (networkError.name === "AbortError") throw networkError;
    throw new ApiError(
      "Tidak dapat menghubungi server. Periksa koneksi jaringan.",
      { status: 0 }
    );
  }

  if (response.status === 401 && !skipAuthRedirect) {
    if (onUnauthorized) onUnauthorized();
  }

  if (!response.ok) {
    const data = await parseBody(response);
    throw new ApiError(data?.detail || `Permintaan gagal (${response.status}).`, {
      status: response.status,
      requestId: data?.request_id || response.headers.get("X-Request-ID"),
      body: data,
    });
  }

  if (blob) return response.blob();
  if (raw) return response;
  if (response.status === 204) return null;
  return parseBody(response);
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (username, password) =>
    request("/api/auth/login", {
      method: "POST",
      body: { username, password },
      token: null,
      skipAuthRedirect: true,
    }),
  me: () => request("/api/auth/me"),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  changePassword: (currentPassword, newPassword) =>
    request("/api/auth/change-password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
    }),
};

// ─── OCR ──────────────────────────────────────────────────────────────────────

export const ocrApi = {
  single: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/api/ocr/upload", { method: "POST", body: form, timeoutMs: 120000 });
  },
  blocks: ({ left, middle, right }) => {
    const form = new FormData();
    form.append("left", left);
    form.append("middle", middle);
    form.append("right", right);
    return request("/api/ocr/upload-blocks", { method: "POST", body: form, timeoutMs: 120000 });
  },
};

// ─── Versions / history ───────────────────────────────────────────────────────

export const versionApi = {
  create: (payload) => request("/api/versions", { method: "POST", body: payload }),
  list: (params = {}, options = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, value);
      }
    });
    const suffix = query.toString() ? `?${query}` : "";
    return request(`/api/versions${suffix}`, options);
  },
  get: (id) => request(`/api/versions/${id}`),
  duplicate: (id) => request(`/api/versions/${id}/duplicate`, { method: "POST" }),
  requestVideo: (id) => request(`/api/versions/${id}/video`, { method: "POST" }),
  archive: (id) => request(`/api/versions/${id}/archive`, { method: "POST" }),
  restore: (id) => request(`/api/versions/${id}/restore`, { method: "POST" }),
  remove: (id) => request(`/api/versions/${id}`, { method: "DELETE" }),
};

export const jobApi = {
  get: (id) => request(`/api/jobs/${id}`),
  recent: (limit = 20) => request(`/api/jobs?limit=${limit}`),
};

// ─── Displays and publishing ──────────────────────────────────────────────────

export const displayApi = {
  list: (branchId, options = {}) =>
    request(`/api/displays${branchId ? `?branch_id=${branchId}` : ""}`, options),
  get: (id) => request(`/api/displays/${id}`),
  approvePairing: (payload) =>
    request("/api/displays/pair", { method: "POST", body: payload }),
  update: (id, payload) =>
    request(`/api/displays/${id}`, { method: "PATCH", body: payload }),
  refresh: (id) => request(`/api/displays/${id}/refresh`, { method: "POST" }),
  revoke: (id) => request(`/api/displays/${id}/revoke`, { method: "POST" }),
  remove: (id) => request(`/api/displays/${id}`, { method: "DELETE" }),
  rollback: (id, idempotencyKey) =>
    request(`/api/displays/${id}/rollback`, {
      method: "POST",
      body: { idempotency_key: idempotencyKey },
    }),
};

export const publicationApi = {
  create: (payload) => request("/api/publications", { method: "POST", body: payload }),
  list: (params = {}, options = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    const suffix = query.toString() ? `?${query}` : "";
    return request(`/api/publications${suffix}`, options);
  },
  cancel: (id) => request(`/api/publications/${id}/cancel`, { method: "POST" }),
};

// ─── Admin ────────────────────────────────────────────────────────────────────

export const userApi = {
  list: (options = {}) => request("/api/users", options),
  create: (payload) => request("/api/users", { method: "POST", body: payload }),
  update: (id, payload) => request(`/api/users/${id}`, { method: "PATCH", body: payload }),
};

export const branchApi = {
  list: (options = {}) => request("/api/branches", options),
  create: (payload) => request("/api/branches", { method: "POST", body: payload }),
  update: (id, payload) =>
    request(`/api/branches/${id}`, { method: "PATCH", body: payload }),
  remove: (id) => request(`/api/branches/${id}`, { method: "DELETE" }),
};

export const dashboardApi = {
  get: (options = {}) => request("/api/dashboard", options),
};

export const auditApi = {
  list: (params = {}, options = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    const suffix = query.toString() ? `?${query}` : "";
    return request(`/api/audit${suffix}`, options);
  },
};

// ─── Media ────────────────────────────────────────────────────────────────────
//
// Media is private, so it cannot be used directly as an <img src>. It is
// fetched with the auth header and turned into an object URL by the caller.

export function fetchMediaBlob(url, options = {}) {
  return request(url, { timeoutMs: 120000, ...options, blob: true });
}

export async function downloadMedia(url, filename) {
  const blob = await fetchMediaBlob(`${url}/download`);
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

// ─── Device (player) ──────────────────────────────────────────────────────────

export const deviceApi = {
  startPairing: () =>
    request("/api/device/pairing/start", {
      method: "POST",
      token: null,
      skipAuthRedirect: true,
    }),
  pairingStatus: (session) =>
    request(`/api/device/pairing/status?device_session=${encodeURIComponent(session)}`, {
      token: null,
      skipAuthRedirect: true,
    }),
  claim: (session) =>
    request("/api/device/pairing/claim", {
      method: "POST",
      body: { device_session: session },
      token: null,
      skipAuthRedirect: true,
    }),
  assignment: (options = {}) =>
    request("/api/device/assignment", {
      ...options,
      tokenKey: DEVICE_TOKEN_KEY,
      skipAuthRedirect: true,
    }),
  heartbeat: (payload, options = {}) =>
    request("/api/device/heartbeat", {
      ...options,
      method: "POST",
      body: payload,
      tokenKey: DEVICE_TOKEN_KEY,
      skipAuthRedirect: true,
    }),
  acknowledge: (payload) =>
    request("/api/device/acknowledge", {
      method: "POST",
      body: payload,
      tokenKey: DEVICE_TOKEN_KEY,
      skipAuthRedirect: true,
    }),
  acknowledgeCommand: (commandId) =>
    request("/api/device/command-ack", {
      method: "POST",
      body: { command_id: commandId },
      tokenKey: DEVICE_TOKEN_KEY,
      skipAuthRedirect: true,
    }),
};

// ─── Websocket ────────────────────────────────────────────────────────────────
//
// A browser cannot set an Authorization header on a websocket, and a token in
// the query string leaks into proxy logs. The subprotocol carries it instead.

export function openSocket(path, token) {
  const base = API_BASE.replace(/^http/, "ws");
  return new WebSocket(`${base}${path}`, ["bearer", token]);
}
