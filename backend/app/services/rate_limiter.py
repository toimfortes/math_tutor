"""In-process fixed-window rate limiter.

Keyed by an arbitrary string (e.g. student id or session id). State is held in
memory, so limits are per-process — adequate for the single-instance vertical
slice; a shared backend (Redis) would be needed for a multi-instance deploy.
"""

from __future__ import annotations

import time
from typing import Callable


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._buckets: dict[str, tuple[float, int]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        window_start, count = self._buckets.get(key, (now, 0))
        if now - window_start >= self._window:
            window_start, count = now, 0
        if count >= self._limit:
            self._buckets[key] = (window_start, count)
            return False
        self._buckets[key] = (window_start, count + 1)
        return True
