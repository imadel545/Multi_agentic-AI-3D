import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0


class TTLCache[T]:
    def __init__(
        self,
        ttl_s: float = 30.0,
        *,
        max_size: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_s <= 0:
            raise ValueError("ttl_s must be greater than zero")
        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        self.ttl_s = ttl_s
        self.max_size = max_size
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._lock = threading.RLock()
        self.stats = CacheStats()

    def get(self, key: str) -> T | None:
        with self._lock:
            now = self._clock()
            item = self._items.get(key)
            if item is None:
                self.stats.misses += 1
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                self.stats.expirations += 1
                self.stats.misses += 1
                return None
            self._items.move_to_end(key)
            self.stats.hits += 1
            return value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            self._items[key] = (now + self.ttl_s, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)
                self.stats.evictions += 1

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired(self._clock())
            return len(self._items)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            self._purge_expired(self._clock())
            return {
                "hits": self.stats.hits,
                "misses": self.stats.misses,
                "evictions": self.stats.evictions,
                "expirations": self.stats.expirations,
                "size": len(self._items),
                "max_size": self.max_size,
            }

    def _purge_expired(self, now: float) -> None:
        expired_keys = [
            key for key, (expires_at, _value) in self._items.items() if expires_at <= now
        ]
        for key in expired_keys:
            self._items.pop(key, None)
        self.stats.expirations += len(expired_keys)
