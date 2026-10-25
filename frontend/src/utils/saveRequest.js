// Keep one retry identity per editor tab, including after a lost response.
const STORAGE_KEY = "pam.save.attempt";

function stableJson(value) {
  if (!value || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
}

function newKey() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) => n.toString(16).padStart(2, "0")).join("");
}

export function createSaveRequest(send, storage) {
  let attempt, pending, controller;
  try {
    storage ??= globalThis.sessionStorage;
    attempt = JSON.parse(storage?.getItem(STORAGE_KEY) || "null");
  } catch { /* Memory-only retries when browser storage is unavailable. */ }

  return {
    save(payload) {
      if (pending) return pending;
      const signature = stableJson(payload);
      if (attempt?.signature !== signature || !attempt?.key) {
        attempt = { signature, key: newKey() };
        try { storage?.setItem(STORAGE_KEY, JSON.stringify(attempt)); } catch { /* quota */ }
      }
      controller = new AbortController();
      pending = Promise.resolve()
        .then(() => send({ ...payload, idempotency_key: attempt.key }, { signal: controller.signal }))
        .then(({ version }) => {
          if (version?.status !== "ready" || !version.png_url) {
            throw new Error("PNG belum siap. Coba simpan ulang dengan data yang sama.");
          }
          return version;
        })
        .finally(() => { pending = null; });
      return pending;
    },
    reset() {
      if (pending) return;
      attempt = null;
      try { storage?.removeItem(STORAGE_KEY); } catch { /* unavailable */ }
    },
    cancel() { controller?.abort(); },
  };
}
