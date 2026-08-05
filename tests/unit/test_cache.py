"""Unit coverage for bounded warm-instance caching."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from unittest.mock import Mock, patch

from backend.core.cache import BoundedTtlCache


def test_ttl_cache_reuses_and_defensively_copies_live_values() -> None:
    loader = Mock(return_value={"companies": ["Acme"]})
    cache: BoundedTtlCache[dict[str, list[str]]] = BoundedTtlCache(max_entries=2)

    first = cache.get_or_compute("directory", ttl_seconds=30, loader=loader)
    first["companies"].append("Mutated")
    second = cache.get_or_compute("directory", ttl_seconds=30, loader=loader)

    assert second == {"companies": ["Acme"]}
    loader.assert_called_once_with()


def test_ttl_cache_reloads_expired_values() -> None:
    loader = Mock(side_effect=[{"version": 1}, {"version": 2}])
    cache: BoundedTtlCache[dict[str, int]] = BoundedTtlCache(max_entries=1)

    with patch("backend.core.cache.monotonic", side_effect=[0.0, 0.0, 31.0, 31.0]):
        first = cache.get_or_compute("overview", ttl_seconds=30, loader=loader)
        second = cache.get_or_compute("overview", ttl_seconds=30, loader=loader)

    assert first == {"version": 1}
    assert second == {"version": 2}
    assert loader.call_count == 2


def test_ttl_cache_coalesces_concurrent_misses_for_one_key() -> None:
    """Concurrent readers should share one loader call instead of stampeding."""

    cache: BoundedTtlCache[dict[str, list[str]]] = BoundedTtlCache(max_entries=2)
    loader_started = Event()
    release_loader = Event()
    loader_count = 0
    loader_count_lock = Lock()

    def loader() -> dict[str, list[str]]:
        nonlocal loader_count
        with loader_count_lock:
            loader_count += 1
        loader_started.set()
        assert release_loader.wait(timeout=2)
        return {"companies": ["Acme"]}

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(
                cache.get_or_compute,
                "directory",
                ttl_seconds=30,
                loader=loader,
            )
            for _ in range(32)
        ]
        assert loader_started.wait(timeout=2)
        release_loader.set()
        results = [future.result(timeout=2) for future in futures]

    assert loader_count == 1
    assert results == [{"companies": ["Acme"]}] * 32
    results[0]["companies"].append("mutated")
    assert results[1] == {"companies": ["Acme"]}


def test_ttl_cache_shares_loader_failure_then_allows_recovery() -> None:
    """A failed single-flight load must wake waiters and must not poison the key."""

    cache: BoundedTtlCache[dict[str, int]] = BoundedTtlCache(max_entries=1)
    loader_started = Event()
    release_loader = Event()
    loader_count = 0
    loader_count_lock = Lock()

    def failing_loader() -> dict[str, int]:
        nonlocal loader_count
        with loader_count_lock:
            loader_count += 1
        loader_started.set()
        assert release_loader.wait(timeout=2)
        raise RuntimeError("temporary database failure")

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(
                cache.get_or_compute,
                "overview",
                ttl_seconds=30,
                loader=failing_loader,
            )
            for _ in range(8)
        ]
        assert loader_started.wait(timeout=2)
        release_loader.set()
        errors = [future.exception(timeout=2) for future in futures]

    assert loader_count == 1
    assert all(isinstance(error, RuntimeError) for error in errors)

    recovered = cache.get_or_compute(
        "overview",
        ttl_seconds=30,
        loader=lambda: {"version": 2},
    )
    assert recovered == {"version": 2}


def test_ttl_cache_clear_does_not_publish_an_inflight_stale_value() -> None:
    """An operator clear must prevent an older in-flight read from being cached."""

    cache: BoundedTtlCache[dict[str, int]] = BoundedTtlCache(max_entries=1)
    stale_loader_started = Event()
    release_stale_loader = Event()

    def stale_loader() -> dict[str, int]:
        stale_loader_started.set()
        assert release_stale_loader.wait(timeout=2)
        return {"version": 1}

    with ThreadPoolExecutor(max_workers=2) as executor:
        stale_future = executor.submit(
            cache.get_or_compute,
            "overview",
            ttl_seconds=30,
            loader=stale_loader,
        )
        assert stale_loader_started.wait(timeout=2)
        cache.clear()
        fresh_future = executor.submit(
            cache.get_or_compute,
            "overview",
            ttl_seconds=30,
            loader=lambda: {"version": 2},
        )
        assert fresh_future.result(timeout=2) == {"version": 2}
        release_stale_loader.set()
        assert stale_future.result(timeout=2) == {"version": 1}

    assert cache.get_or_compute(
        "overview",
        ttl_seconds=30,
        loader=lambda: {"version": 3},
    ) == {"version": 2}
