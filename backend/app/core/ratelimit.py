"""Fixed-window rate limiter for login and pairing.

Deliberately in-process and in-memory. It raises the cost of guessing a
password or a pairing code, which is what it is for. It is **not** a
distributed limiter: with several API processes each keeps its own counters,
so the effective limit is per process. That is documented in deployment.md,
and the pairing code has its own per-code attempt counter in the database as a
second line of defence that does survive multiple processes.
"""

import threading
import time
from typing import Dict, Tuple


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Count one attempt. Returns False when the caller is over budget."""
        now = time.monotonic()
        with self._lock:
            count, window_start = self._hits.get(key, (0, now))

            if now - window_start >= self.window_seconds:
                count, window_start = 0, now

            count += 1
            self._hits[key] = (count, window_start)

            if len(self._hits) > 4096:
                self._evict(now)

            return count <= self.max_attempts

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def retry_after(self, key: str) -> int:
        with self._lock:
            entry = self._hits.get(key)
        if not entry:
            return 0
        _, window_start = entry
        remaining = self.window_seconds - (time.monotonic() - window_start)
        return max(0, int(remaining))

    def _evict(self, now: float) -> None:
        stale = [k for k, (_, start) in self._hits.items() if now - start >= self.window_seconds]
        for key in stale:
            self._hits.pop(key, None)
