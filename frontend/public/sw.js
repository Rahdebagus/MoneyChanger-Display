/* ── PAM Rate Display service worker ───────────────────────────────────────────
 *
 * Its only job is the app shell. Without it, reloading a TV while the network
 * is down would fail to fetch index.html and the JS bundle, and the screen
 * would go blank even though the board image is sitting in Cache Storage.
 *
 * Board media is deliberately NOT handled here. It needs an Authorization
 * header and is cached by the player itself (features/player/mediaCache.js),
 * which can also apply the eviction policy that protects whatever is on
 * screen right now.
 *
 * Strategy:
 *   - navigations: network first, fall back to the cached shell when offline
 *   - hashed build assets: cache first (the hash makes them immutable)
 *   - everything else, including /api: straight to the network, never cached
 */

const SHELL_CACHE = "pam-shell-v1";
const SHELL_URL = "/index.html";

const PRECACHE = [SHELL_URL, "/favicon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("pam-shell-") && key !== SHELL_CACHE)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

function isBuildAsset(url) {
  return url.origin === self.location.origin && url.pathname.startsWith("/assets/");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // API traffic is never cached here: it is authenticated, it changes, and
  // the database is the source of truth for what a display should show.
  if (url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches
            .open(SHELL_CACHE)
            .then((cache) => cache.put(SHELL_URL, copy))
            .catch(() => undefined);
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(SHELL_URL);
          return (
            cached ||
            new Response(
              "<!doctype html><meta charset=utf-8><title>Offline</title>" +
                "<body style=\"background:#000;color:#fff;font-family:system-ui;" +
                "display:flex;align-items:center;justify-content:center;height:100vh;" +
                "margin:0;text-align:center\">" +
                "<div><div style=\"font-size:9vmin\">📡</div>" +
                "<div style=\"font-size:4vmin;font-weight:700\">Tidak ada koneksi</div></div>",
              { headers: { "Content-Type": "text/html; charset=utf-8" } }
            )
          );
        })
    );
    return;
  }

  if (isBuildAsset(url)) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches
                .open(SHELL_CACHE)
                .then((cache) => cache.put(request, copy))
                .catch(() => undefined);
            }
            return response;
          })
      )
    );
  }
});
