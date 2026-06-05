import time
from dataclasses import dataclass


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0


class TTLCache[T]:
    def __init__(self, ttl_s: float = 30.0) -> None:
        self.ttl_s = ttl_s
        self._items: dict[str, tuple[float, T]] = {}
        self.stats = CacheStats()

    def get(self, key: str) -> T | None:
        item = self._items.get(key)
        if item is None:
            self.stats.misses += 1
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._items.pop(key, None)
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return value

    def set(self, key: str, value: T) -> None:
        self._items[key] = (time.time() + self.ttl_s, value)

    def clear(self) -> None:
        self._items.clear()

    def snapshot(self) -> dict[str, int]:
        return {"hits": self.stats.hits, "misses": self.stats.misses}
