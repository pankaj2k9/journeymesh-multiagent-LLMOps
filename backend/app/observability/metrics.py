"""In-memory counters and timers exposed by the health endpoint."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

_lock = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
_timers: dict[str, list[int]] = defaultdict(list)
_MAX_SAMPLES = 500


def increment(name: str, value: int = 1, **labels: Any) -> None:
    key = _key(name, labels)
    with _lock:
        _counters[key] += value


def observe(name: str, latency_ms: int, **labels: Any) -> None:
    key = _key(name, labels)
    with _lock:
        samples = _timers[key]
        samples.append(latency_ms)
        if len(samples) > _MAX_SAMPLES:
            del samples[: len(samples) - _MAX_SAMPLES]


def snapshot() -> dict[str, Any]:
    with _lock:
        counters = dict(_counters)
        timers = {
            key: {
                "count": len(values),
                "avg_ms": round(sum(values) / len(values), 2) if values else 0,
                "p95_ms": _percentile(values, 95),
                "max_ms": max(values) if values else 0,
            }
            for key, values in _timers.items()
        }
    return {"counters": counters, "timers": timers}


def reset() -> None:
    with _lock:
        _counters.clear()
        _timers.clear()


def _key(name: str, labels: dict[str, Any]) -> str:
    if not labels:
        return name
    rendered = ",".join(f"{k}={v}" for k, v in sorted(labels.items()) if v is not None)
    return f"{name}{{{rendered}}}" if rendered else name


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(int(round((percentile / 100) * len(ordered) + 0.5)) - 1, len(ordered) - 1)
    return ordered[max(index, 0)]
