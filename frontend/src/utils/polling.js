// One request at a time; timers stop while the admin tab is hidden/offline.
export function startPolling(task, {
  intervalMs = 0,
  pauseWhenHidden = true,
  documentTarget = globalThis.document,
  windowTarget = globalThis.window,
} = {}) {
  let timer;
  let controller;
  let running = false;
  let disposed = false;
  let queued = false;
  let failures = 0;
  let lastRun = 0;

  const available = () => !disposed
    && (!pauseWhenHidden || documentTarget?.visibilityState !== "hidden")
    && globalThis.navigator?.onLine !== false;

  function schedule(delay) {
    clearTimeout(timer);
    if (available()) timer = setTimeout(run, delay);
  }

  async function run() {
    if (!available() || running) return;
    running = true;
    controller = new AbortController();
    try {
      await task(controller.signal);
      failures = 0;
    } catch (error) {
      if (error.name !== "AbortError") failures += 1;
    } finally {
      running = false;
      lastRun = Date.now();
      if (queued) {
        queued = false;
        schedule(0);
      } else if (intervalMs > 0) {
        schedule(Math.min(intervalMs * 2 ** Math.min(failures, 3), 300000));
      }
    }
  }

  function refresh() {
    clearTimeout(timer);
    if (running) queued = true;
    else schedule(0);
  }

  function resume() {
    clearTimeout(timer);
    if (!available()) {
      controller?.abort();
      return;
    }
    if (running) {
      if (controller?.signal.aborted) queued = true;
      return;
    }
    const elapsed = Date.now() - lastRun;
    if (!lastRun || elapsed >= intervalMs) schedule(0);
    else if (intervalMs > 0) schedule(intervalMs - elapsed);
  }

  if (pauseWhenHidden) documentTarget?.addEventListener("visibilitychange", resume);
  windowTarget?.addEventListener("online", refresh);
  windowTarget?.addEventListener("offline", resume);
  schedule(0);

  return {
    refresh,
    stop() {
      disposed = true;
      clearTimeout(timer);
      controller?.abort();
      if (pauseWhenHidden) documentTarget?.removeEventListener("visibilitychange", resume);
      windowTarget?.removeEventListener("online", refresh);
      windowTarget?.removeEventListener("offline", resume);
    },
  };
}
