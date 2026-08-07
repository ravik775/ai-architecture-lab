"""Bounded, in-memory TTL cache with LRU eviction.

Single-process only - documented limitation: a horizontally-scaled
deployment would lose cross-replica cache coherence and request
coalescing. See architecture notes for the Redis migration path.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict

from app.config.settings import CacheSettings
from app.domain.models import WeatherObservation


class InMemoryWeatherCache:
    def __init__(self, settings: CacheSettings) -> None:
        self._settings = settings
        self._store: OrderedDict[str, tuple[WeatherObservation, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> WeatherObservation | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            observation, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return observation

    async def set(self, key: str, value: WeatherObservation) -> None:
        async with self._lock:
            expires_at = time.monotonic() + self._settings.current_weather_ttl_seconds
            self._store[key] = (value, expires_at)
            self._store.move_to_end(key)
            while len(self._store) > self._settings.max_entries:
                self._store.popitem(last=False)

    def size(self) -> int:
        return len(self._store)
