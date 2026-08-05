"""Small, bounded warm-instance cache for stable private read models."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, RLock
from time import monotonic
from typing import Generic, TypeVar


ValueT = TypeVar("ValueT")


@dataclass(slots=True)
class _CacheEntry(Generic[ValueT]):
    expires_at: float
    value: ValueT


@dataclass(slots=True)
class _PendingLoad(Generic[ValueT]):
    """Coordinate callers waiting for the same cache miss."""

    generation: int
    completed: Event = field(default_factory=Event)
    value: ValueT | None = None
    error: BaseException | None = None


class BoundedTtlCache(Generic[ValueT]):
    """Cache copied values for a short TTL and cap warm-instance memory use."""

    def __init__(self, *, max_entries: int = 32) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive.")
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _CacheEntry[ValueT]] = OrderedDict()
        self._pending_loads: dict[str, _PendingLoad[ValueT]] = {}
        self._generation = 0
        self._lock = RLock()

    def get_or_compute(
        self,
        key: str,
        *,
        ttl_seconds: int,
        loader: Callable[[], ValueT],
    ) -> ValueT:
        """Return a defensive copy of a live hit or compute and cache a value."""

        if ttl_seconds <= 0:
            return loader()

        now = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > now:
                self._entries.move_to_end(key)
                return deepcopy(entry.value)
            if entry is not None:
                del self._entries[key]

            pending = self._pending_loads.get(key)
            is_loader = pending is None
            if pending is None:
                pending = _PendingLoad(generation=self._generation)
                self._pending_loads[key] = pending

        if not is_loader:
            pending.completed.wait()
            if pending.error is not None:
                raise pending.error
            return deepcopy(pending.value)

        try:
            loaded = loader()
            cached_value = deepcopy(loaded)
        except BaseException as exc:
            with self._lock:
                pending.error = exc
                if self._pending_loads.get(key) is pending:
                    self._pending_loads.pop(key, None)
                pending.completed.set()
            raise

        with self._lock:
            pending.value = cached_value
            # A clear issued while the loader was running must win. Callers
            # already waiting for this result may receive it, but a later read
            # must load fresh state instead of reviving the cleared entry.
            if pending.generation == self._generation:
                self._entries[key] = _CacheEntry(
                    expires_at=monotonic() + ttl_seconds,
                    value=deepcopy(cached_value),
                )
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
            if self._pending_loads.get(key) is pending:
                self._pending_loads.pop(key, None)
            pending.completed.set()
        return loaded

    def clear(self) -> None:
        """Discard all warm-instance entries, primarily for tests and operations."""

        with self._lock:
            self._entries.clear()
            self._generation += 1
            self._pending_loads.clear()


def stable_read_cache_ttl_seconds() -> int:
    """Enable stable-read caching only in deployed preview/production runtimes."""

    from backend.settings import get_settings

    settings = get_settings()
    if settings.environment not in {"preview", "production"}:
        return 0
    return settings.stable_read_cache_ttl_seconds


__all__ = ["BoundedTtlCache", "stable_read_cache_ttl_seconds"]
