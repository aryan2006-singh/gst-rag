"""Response cache and per-client rate limiting for the API.

Both are in-process and in-memory on purpose. The service is one process
serving a read-only index, so there is nothing to keep consistent across
replicas, and adding Redis to a portfolio deploy would cost more than it saves.
If it ever runs as several replicas, each keeps its own cache and its own
limit, which only makes the limit looser.

Both are thread-safe: `/query` is a plain `def`, so FastAPI calls it from a
worker thread pool.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

V = TypeVar("V")


class LRUCache(Generic[V]):
    """Bounded least-recently-used cache. `maxsize=0` disables it."""

    def __init__(self, maxsize: int = 256) -> None:
        self.maxsize = maxsize
        self._data: OrderedDict[Hashable, V] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> V | None:
        with self._lock:
            if key not in self._data:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return self._data[key]

    def put(self, key: Hashable, value: V) -> None:
        if self.maxsize <= 0:
            return
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def stats(self) -> dict:
        return {"size": len(self), "maxsize": self.maxsize, "hits": self.hits, "misses": self.misses}


class RateLimiter:
    """Token bucket per client key.

    Each client gets `per_minute` tokens of burst and refills at
    `per_minute / 60` tokens a second. `per_minute=0` disables limiting.
    Idle buckets are dropped so the table can't grow without bound.
    """

    def __init__(
        self,
        per_minute: int = 60,
        clock: Callable[[], float] = time.monotonic,
        max_clients: int = 10_000,
    ) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self.clock = clock
        self.max_clients = max_clients
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, updated)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.capacity > 0

    def check(self, key: str) -> float:
        """Take one token for `key`. Returns 0 if allowed, else seconds to wait."""
        if not self.enabled:
            return 0.0
        now = self.clock()
        with self._lock:
            tokens, updated = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - updated) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                if len(self._buckets) > self.max_clients:
                    self._evict_full(now)
                return 0.0
            self._buckets[key] = (tokens, now)
            return (1.0 - tokens) / self.rate

    def _evict_full(self, now: float) -> None:
        # A bucket that has refilled to capacity carries no state worth keeping.
        full_after = self.capacity / self.rate
        for key in [k for k, (_, t) in self._buckets.items() if now - t >= full_after]:
            del self._buckets[key]


def client_key(peer: str | None, forwarded_for: str | None, trusted_hops: int) -> str:
    """The address to rate-limit on.

    Behind a reverse proxy every request comes from the proxy's address, so the
    real client has to come from X-Forwarded-For. But the client can write
    anything it likes at the *front* of that header; only the entries appended
    by proxies we trust are reliable. With `trusted_hops` proxies in front of
    us, the client is the `trusted_hops`-th entry from the right.
    """
    if trusted_hops > 0 and forwarded_for:
        hops = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        if hops:
            return hops[-min(trusted_hops, len(hops))]
    return peer or "unknown"


def retry_after_header(seconds: float) -> str:
    return str(max(1, math.ceil(seconds)))
