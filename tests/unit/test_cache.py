from concurrent.futures import ThreadPoolExecutor

import pytest

from core.performance.cache import TTLCache


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_ttl_cache_is_lru_bounded() -> None:
    clock = ManualClock()
    cache = TTLCache[str](ttl_s=30, max_size=2, clock=clock)
    cache.set("a", "A")
    cache.set("b", "B")
    assert cache.get("a") == "A"

    cache.set("c", "C")

    assert cache.get("b") is None
    assert cache.get("a") == "A"
    assert cache.get("c") == "C"
    assert cache.snapshot() == {
        "hits": 3,
        "misses": 1,
        "evictions": 1,
        "expirations": 0,
        "size": 2,
        "max_size": 2,
    }


def test_ttl_cache_purges_expired_entries_without_counting_cache_misses() -> None:
    clock = ManualClock()
    cache = TTLCache[int](ttl_s=5, max_size=4, clock=clock)
    cache.set("a", 1)
    cache.set("b", 2)
    clock.advance(5)

    assert len(cache) == 0
    assert cache.snapshot()["expirations"] == 2
    assert cache.snapshot()["misses"] == 0
    assert cache.get("a") is None
    assert cache.snapshot()["misses"] == 1


def test_ttl_cache_remains_bounded_under_concurrent_access() -> None:
    cache = TTLCache[int](ttl_s=60, max_size=32)

    def exercise(index: int) -> None:
        key = f"key-{index % 64}"
        cache.set(key, index)
        cache.get(key)

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(exercise, range(2_000)))

    assert len(cache) <= 32
    assert cache.snapshot()["size"] <= cache.snapshot()["max_size"]
    assert cache.snapshot()["evictions"] > 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"ttl_s": 0}, "ttl_s must be greater than zero"),
        ({"ttl_s": 1, "max_size": 0}, "max_size must be at least 1"),
    ],
)
def test_ttl_cache_rejects_invalid_bounds(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TTLCache(**kwargs)
