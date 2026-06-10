"""InsightCache — TTL + LRU response cache for the insights endpoint.

Why: insights are read far more often than the ledger changes. A short
TTL cache lets repeated reads skip Firestore aggregation and Gemini
calls entirely — the single biggest efficiency win per request.
"""
import time
from collections import OrderedDict


class InsightCache:
    """Small in-process cache with TTL expiry and LRU eviction."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 256):
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries = OrderedDict()

    def get(self, key):
        """Return the cached value or None if absent/expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, stored_at = entry
        if time.monotonic() - stored_at > self._ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key, value) -> None:
        """Store a value, evicting the least-recently-used on overflow."""
        self._entries[key] = (value, time.monotonic())
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def invalidate_prefix(self, prefix) -> None:
        """Drop entries whose tuple key starts with `prefix` (e.g. a session)."""
        stale = [key for key in self._entries if key[: len(prefix)] == prefix]
        for key in stale:
            del self._entries[key]
