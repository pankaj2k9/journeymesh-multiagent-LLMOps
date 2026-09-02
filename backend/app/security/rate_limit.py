"""Fixed-window rate limiting with a per-client bucket.

The limiter is intentionally dependency free so it also works on serverless
runtimes where a shared cache may not be available. For a multi-instance
deployment, swap :class:`InMemoryRateLimiter` for a Redis-backed one - the
interface is the only thing the middleware depends on.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_after: int


class RateLimiter(Protocol):
    def hit(self, key: str) -> RateLimitResult: ...


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = {}

    def hit(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            count, window_start = self._buckets.get(key, (0, now))
            if now - window_start >= self.window_seconds:
                count, window_start = 0, now
            count += 1
            self._buckets[key] = (count, window_start)
            self._prune(now)

        reset_after = int(max(0, self.window_seconds - (now - window_start)))
        allowed = count <= self.limit
        remaining = max(0, self.limit - count)
        return RateLimitResult(
            allowed=allowed, limit=self.limit, remaining=remaining, reset_after=reset_after
        )

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _prune(self, now: float) -> None:
        if len(self._buckets) < 2048:
            return
        stale = [
            key
            for key, (_, started) in self._buckets.items()
            if now - started >= self.window_seconds * 2
        ]
        for key in stale:
            self._buckets.pop(key, None)


_limiter: Optional[InMemoryRateLimiter] = None


def get_rate_limiter(*, limit: int, window_seconds: int) -> InMemoryRateLimiter:
    global _limiter
    if _limiter is None or _limiter.limit != limit or _limiter.window_seconds != window_seconds:
        _limiter = InMemoryRateLimiter(limit=limit, window_seconds=window_seconds)
    return _limiter


def reset_rate_limiter() -> None:
    global _limiter
    if _limiter is not None:
        _limiter.reset()
    _limiter = None
