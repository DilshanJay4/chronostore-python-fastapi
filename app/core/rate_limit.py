"""A small in-process sliding-window rate limiter.

Suitable for a single API process. When running several workers or replicas, enforce
limits at the reverse proxy / API gateway or move this to a shared store (e.g. Redis);
see README "Operational limitations".
"""

import math
import threading
import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, *, now: float | None = None) -> int | None:
        """Record an attempt. Returns `None` if allowed, else seconds until retry."""
        current = time.monotonic() if now is None else now
        window_start = current - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= window_start:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                return max(1, math.ceil(hits[0] + self.window_seconds - current))
            hits.append(current)
            if len(self._hits) > 10_000:  # bound memory under key-spraying attacks
                self._evict_stale(window_start)
            return None

    def _evict_stale(self, window_start: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= window_start]
        for key in stale:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
