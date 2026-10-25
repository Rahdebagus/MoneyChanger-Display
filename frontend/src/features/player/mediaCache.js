// ─── Player Media Cache ───────────────────────────────────────────────────────
//
// A TV must keep showing the right board when the network drops, including
// across a reload. That rules out memory and localStorage: binary media is too
// large for localStorage, and memory does not survive a refresh.
//
// Media bytes therefore live in the Cache Storage API, and the small pointer
// describing what is cached lives in localStorage. Eviction is oldest-first
// and always protects the version currently on screen.

const CACHE_NAME = "pam-player-media-v1";
const STATE_KEY = "pam.player.state";
const MAX_ENTRIES = 6;

function cachesAvailable() {
  return typeof caches !== "undefined";
}

/** Cache keys are synthetic: the real URL needs an auth header to fetch. */
function cacheKey(mediaUrl) {
  return `https://pam-player.local/${encodeURIComponent(mediaUrl)}`;
}

export async function putMedia(mediaUrl, blob) {
  if (!cachesAvailable()) return false;
  try {
    const cache = await caches.open(CACHE_NAME);
    await cache.put(
      cacheKey(mediaUrl),
      new Response(blob, {
        headers: {
          "Content-Type": blob.type || "application/octet-stream",
          "X-Cached-At": String(Date.now()),
        },
      })
    );
    return true;
  } catch {
    return false;
  }
}

export async function getMedia(mediaUrl) {
  if (!cachesAvailable()) return null;
  try {
    const cache = await caches.open(CACHE_NAME);
    const response = await cache.match(cacheKey(mediaUrl));
    if (!response) return null;
    return await response.blob();
  } catch {
    return null;
  }
}

export async function hasMedia(mediaUrl) {
  if (!cachesAvailable()) return false;
  try {
    const cache = await caches.open(CACHE_NAME);
    return Boolean(await cache.match(cacheKey(mediaUrl)));
  } catch {
    return false;
  }
}

/**
 * Trim the cache, never evicting anything the player still needs on screen.
 */
export async function evictExcept(protectedUrls = []) {
  if (!cachesAvailable()) return;
  try {
    const cache = await caches.open(CACHE_NAME);
    const keys = await cache.keys();
    if (keys.length <= MAX_ENTRIES) return;

    const protectedKeys = new Set(protectedUrls.filter(Boolean).map(cacheKey));

    const entries = await Promise.all(
      keys.map(async (request) => {
        const response = await cache.match(request);
        const cachedAt = Number(response?.headers.get("X-Cached-At") || 0);
        return { request, cachedAt };
      })
    );

    entries
      .filter((entry) => !protectedKeys.has(entry.request.url))
      .sort((a, b) => a.cachedAt - b.cachedAt)
      .slice(0, Math.max(0, keys.length - MAX_ENTRIES))
      .forEach((entry) => cache.delete(entry.request));
  } catch {
    /* eviction is best effort */
  }
}

// ─── Pointer state ────────────────────────────────────────────────────────────
//
// Small enough for localStorage, and it must survive a reload so an offline
// TV knows what it was showing before the power blinked.

export function readState() {
  try {
    const raw = window.localStorage.getItem(STATE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function writeState(state) {
  try {
    window.localStorage.setItem(STATE_KEY, JSON.stringify(state));
  } catch {
    /* a kiosk with storage disabled still works online */
  }
}

export function clearState() {
  try {
    window.localStorage.removeItem(STATE_KEY);
  } catch {
    /* ignore */
  }
}

export async function clearAll() {
  clearState();
  if (!cachesAvailable()) return;
  try {
    await caches.delete(CACHE_NAME);
  } catch {
    /* ignore */
  }
}
