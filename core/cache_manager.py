"""
Two-tier cache manager: a fast in-memory layer backed by the persisted
``cache`` database table, so expensive operations (competitor research,
AI completions) survive process restarts until their TTL expires.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from config import get_settings
from core.logger import get_logger
from database.models.cache import Cache
from database.session import session_scope

logger = get_logger(__name__)


class CacheManager:
    """
    Provides ``get``/``set``/``delete``/``clear_expired`` semantics over a
    namespaced key/value store. Reads check the in-memory layer first;
    on a miss they fall through to the database and repopulate memory.
    """

    def __init__(self, namespace: str = "default") -> None:
        """
        Args:
            namespace: Logical partition for cache keys (e.g. ``"research"``,
                ``"ai_completions"``), preventing collisions between subsystems.
        """
        self.namespace = namespace
        self._memory: dict[str, tuple[Any, datetime | None]] = {}
        self._settings = get_settings()

    def _full_key(self, key: str) -> str:
        """Build the namespaced cache key used for both memory and DB storage."""
        return f"{self.namespace}:{key}"

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a cached value, or ``default`` if missing/expired.

        Checks memory first, then the persisted database table, honouring
        expiry in both tiers.
        """
        full_key = self._full_key(key)
        now = datetime.now(timezone.utc)

        if full_key in self._memory:
            value, expires_at = self._memory[full_key]
            if expires_at is None or expires_at > now:
                return value
            del self._memory[full_key]

        with session_scope() as session:
            stmt = select(Cache).where(Cache.cache_key == full_key)
            row = session.execute(stmt).scalars().first()
            if row is None:
                return default
            if row.expires_at is not None and row.expires_at <= now:
                session.delete(row)
                return default
            value = row.value
            self._memory[full_key] = (value, row.expires_at)
            return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """
        Store ``value`` under ``key`` with an optional TTL.

        Args:
            key: The cache key (namespaced automatically).
            value: A JSON-serialisable value.
            ttl_seconds: Time-to-live in seconds. Defaults to the app-wide
                ``CACHE_TTL_SECONDS`` setting when omitted.
        """
        full_key = self._full_key(key)
        ttl = ttl_seconds if ttl_seconds is not None else self._settings.cache_ttl_seconds
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl) if ttl and ttl > 0 else None
        )

        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            logger.error("Refusing to cache non-JSON-serialisable value for key '{}': {}", key, exc)
            return

        self._memory[full_key] = (value, expires_at)

        with session_scope() as session:
            stmt = select(Cache).where(Cache.cache_key == full_key)
            row = session.execute(stmt).scalars().first()
            if row is None:
                row = Cache(cache_key=full_key, value=value, expires_at=expires_at, namespace=self.namespace)
                session.add(row)
            else:
                row.value = value
                row.expires_at = expires_at
        logger.debug("Cached key '{}' (ttl={}s)", full_key, ttl)

    def delete(self, key: str) -> None:
        """Remove a key from both the memory and database layers."""
        full_key = self._full_key(key)
        self._memory.pop(full_key, None)
        with session_scope() as session:
            stmt = select(Cache).where(Cache.cache_key == full_key)
            row = session.execute(stmt).scalars().first()
            if row is not None:
                session.delete(row)

    def clear_namespace(self) -> int:
        """Delete every cache entry belonging to this manager's namespace."""
        keys_to_drop = [k for k in self._memory if k.startswith(f"{self.namespace}:")]
        for k in keys_to_drop:
            del self._memory[k]

        with session_scope() as session:
            stmt = select(Cache).where(Cache.namespace == self.namespace)
            rows = session.execute(stmt).scalars().all()
            count = len(rows)
            for row in rows:
                session.delete(row)
        logger.info("Cleared {} cache entries in namespace '{}'.", count, self.namespace)
        return count

    @staticmethod
    def clear_all_expired() -> int:
        """Purge every expired entry across all namespaces. Returns the count removed."""
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            stmt = select(Cache).where(Cache.expires_at.is_not(None), Cache.expires_at <= now)
            rows = session.execute(stmt).scalars().all()
            count = len(rows)
            for row in rows:
                session.delete(row)
        if count:
            logger.info("Purged {} expired cache entries.", count)
        return count
