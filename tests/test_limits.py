"""Response cache and rate limiting: unit tests plus the /query wiring."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from src.serve import app as app_module  # noqa: E402
from src.serve.limits import LRUCache, RateLimiter, client_key, retry_after_header  # noqa: E402
from src.retrieve.rerank import StubReranker  # noqa: E402
from tests.test_serve_api import make_state  # noqa: E402


# ------------------------------------------------------------------ LRU cache
def test_lru_evicts_least_recently_used():
    cache: LRUCache[int] = LRUCache(maxsize=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # a is now most recent
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1 and cache.get("c") == 3
    assert cache.stats() == {"size": 2, "maxsize": 2, "hits": 3, "misses": 1}


def test_lru_size_zero_disables():
    cache: LRUCache[int] = LRUCache(maxsize=0)
    cache.put("a", 1)
    assert cache.get("a") is None
    assert len(cache) == 0


# --------------------------------------------------------------- rate limiter
class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_allows_burst_then_blocks_then_refills():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=3, clock=clock)
    assert [limiter.check("ip") for _ in range(3)] == [0.0, 0.0, 0.0]
    wait = limiter.check("ip")
    assert wait == pytest.approx(20.0)  # 3/min refills one token every 20s
    clock.now += 20
    assert limiter.check("ip") == 0.0
    assert limiter.check("ip") > 0


def test_rate_limiter_is_per_client():
    limiter = RateLimiter(per_minute=1, clock=FakeClock())
    assert limiter.check("a") == 0.0
    assert limiter.check("a") > 0
    assert limiter.check("b") == 0.0


def test_rate_limiter_zero_disables():
    limiter = RateLimiter(per_minute=0)
    assert not limiter.enabled
    assert all(limiter.check("ip") == 0.0 for _ in range(100))


def test_rate_limiter_drops_idle_buckets():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, clock=clock, max_clients=2)
    limiter.check("a")
    limiter.check("b")
    clock.now += 120  # both refilled long ago
    limiter.check("c")
    assert set(limiter._buckets) == {"c"}


def test_retry_after_is_a_whole_number_of_at_least_one_second():
    assert retry_after_header(0.2) == "1"
    assert retry_after_header(19.1) == "20"


# ----------------------------------------------------------------- client key
def test_client_key_ignores_forwarded_for_without_trusted_proxies():
    assert client_key("10.0.0.1", "6.6.6.6", trusted_hops=0) == "10.0.0.1"


def test_client_key_takes_the_entry_the_trusted_proxy_appended():
    # The client wrote "6.6.6.6" itself; the proxy appended the real address.
    assert client_key("10.0.0.1", "6.6.6.6, 203.0.113.9", trusted_hops=1) == "203.0.113.9"
    assert client_key("10.0.0.1", "6.6.6.6, 203.0.113.9, 10.1.1.1", trusted_hops=2) == "203.0.113.9"


def test_client_key_falls_back_to_peer():
    assert client_key("10.0.0.1", None, trusted_hops=1) == "10.0.0.1"
    assert client_key(None, None, trusted_hops=0) == "unknown"


# --------------------------------------------------------------- API wiring
@pytest.fixture
def client(monkeypatch):
    state = make_state(StubReranker())
    state["cache"] = LRUCache(maxsize=16)
    state["limiter"] = RateLimiter(per_minute=0)
    state["trusted_proxy_hops"] = 0
    monkeypatch.setattr(app_module, "STATE", state)
    return TestClient(app_module.app), state


def test_repeat_query_is_served_from_cache(client):
    http, state = client
    first = http.post("/query", json={"question": "input tax credit time limit"}).json()
    second = http.post("/query", json={"question": "  Input TAX credit   time limit "}).json()
    assert first["trace"]["cache"] == "miss"
    assert second["trace"]["cache"] == "hit"
    assert second["question"] == "  Input TAX credit   time limit "
    assert [c["chunk_id"] for c in second["citations"]] == [c["chunk_id"] for c in first["citations"]]
    assert state["cache"].stats()["hits"] == 1


def test_cache_key_includes_top_k_and_variant(client):
    http, _ = client
    q = "input tax credit time limit"
    http.post("/query", json={"question": q, "top_k": 3})
    assert http.post("/query", json={"question": q, "top_k": 4}).json()["trace"]["cache"] == "miss"
    other = http.post("/query", json={"question": q, "top_k": 3, "variant": "BM25 only"}).json()
    assert other["trace"]["cache"] == "miss"
    assert other["trace"]["config"] == "BM25 only"


def test_query_returns_429_with_retry_after(client):
    http, state = client
    state["limiter"] = RateLimiter(per_minute=2)
    ok = [http.post("/query", json={"question": "input tax credit"}).status_code for _ in range(2)]
    blocked = http.post("/query", json={"question": "input tax credit"})
    assert ok == [200, 200]
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_health_reports_cache_stats(client):
    http, _ = client
    http.post("/query", json={"question": "input tax credit"})
    assert http.get("/health").json()["cache"]["size"] == 1


def test_bad_limit_env_is_reported(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "lots")
    with pytest.raises(ValueError, match="RATE_LIMIT_PER_MINUTE"):
        app_module.load_limits()
