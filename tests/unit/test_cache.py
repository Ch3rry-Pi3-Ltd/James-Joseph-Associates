"""Unit coverage for bounded warm-instance caching."""

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
