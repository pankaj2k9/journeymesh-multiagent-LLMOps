"""A circuit breaker for provider calls.

A provider that is failing should be *asked* less, not more. Without a breaker,
every search waits the full timeout on a dead endpoint, and a provider outage
turns into a site-wide latency problem - the failure mode that takes down the
page that was only partly dependent on it.

Three states, the standard ones:

    CLOSED  - calls go through; consecutive failures are counted
    OPEN    - calls are refused immediately for a cool-off period
    HALF_OPEN - one probe is allowed; success closes, failure re-opens

State is per process and in memory. That is the right scope here: each worker
learns about the provider it is actually talking to, and a shared store would
add a dependency whose own outage would then need a breaker.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Literal

State = Literal["closed", "open", "half_open"]

DEFAULT_FAILURE_THRESHOLD = 4
DEFAULT_RESET_SECONDS = 30.0


@dataclass
class Breaker:
    name: str
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    reset_seconds: float = DEFAULT_RESET_SECONDS

    failures: int = 0
    successes: int = 0
    total_calls: int = 0
    opened_at: float | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def state(self) -> State:
        if self.opened_at is None:
            return "closed"
        if time.monotonic() - self.opened_at >= self.reset_seconds:
            return "half_open"
        return "open"

    def allows(self) -> bool:
        """Whether a call may be attempted right now."""
        return self.state != "open"

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.successes += 1
            self.total_calls += 1
            self.opened_at = None
            self.last_success_at = time.time()

    def record_failure(self, error: str | None = None) -> None:
        with self._lock:
            self.failures += 1
            self.total_calls += 1
            self.last_failure_at = time.time()
            self.last_error = error
            if self.failures >= self.failure_threshold:
                self.opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self.failures = 0
            self.successes = 0
            self.total_calls = 0
            self.opened_at = None
            self.last_error = None

    def health(self) -> str:
        """UP / DEGRADED / DOWN, for the provider health dashboard."""
        if self.state == "open":
            return "DOWN"
        if self.failures:
            return "DEGRADED"
        return "UP"

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "state": self.state,
            "health": self.health(),
            "failures": self.failures,
            "successes": self.successes,
            "total_calls": self.total_calls,
            "success_rate": (
                round(self.successes / self.total_calls, 4) if self.total_calls else None
            ),
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "last_error": self.last_error,
        }


_breakers: dict[str, Breaker] = {}
_registry_lock = threading.Lock()


def breaker_for(name: str) -> Breaker:
    with _registry_lock:
        if name not in _breakers:
            _breakers[name] = Breaker(name=name)
        return _breakers[name]


def snapshot() -> list[dict[str, object]]:
    with _registry_lock:
        return [breaker.to_dict() for breaker in _breakers.values()]


def reset_all() -> None:
    with _registry_lock:
        for breaker in _breakers.values():
            breaker.reset()
        _breakers.clear()


__all__ = ["Breaker", "breaker_for", "reset_all", "snapshot"]
