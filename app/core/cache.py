"""
Simple in-memory cache with TTL for external API responses.

This cache reduces load on external services (SoloPool, CKPool, etc.)
and improves widget response times by avoiding redundant API calls.

Note: Cryptocurrency prices use database cache (CryptoPrice table) 
instead of this in-memory cache for persistence across restarts.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
import asyncio


class SimpleCache:
    """Thread-safe in-memory cache with TTL (time-to-live)"""
    
    def __init__(self):
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get cached value if not expired.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if datetime.utcnow() < expiry:
                    return value
                else:
                    # Expired - remove from cache
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: Any, ttl_seconds: int):
        """
        Set cached value with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds
        """
        async with self._lock:
            expiry = datetime.utcnow() + timedelta(seconds=ttl_seconds)
            self._cache[key] = (value, expiry)
    
    async def get_or_fetch(
        self, 
        key: str, 
        fetch_func: Callable, 
        ttl_seconds: int = 300
    ) -> Any:
        """
        Get from cache or fetch and cache if not found.
        
        Args:
            key: Cache key
            fetch_func: Async function to fetch data if not cached
            ttl_seconds: Time to live in seconds (default: 5 minutes)
        
        Returns:
            Cached or freshly fetched value
        
        Example:
            >>> async def fetch_pool_stats():
            ...     return await SolopoolService.get_btc_account_stats("user")
            >>> stats = await api_cache.get_or_fetch("solopool_btc_user", fetch_pool_stats, ttl_seconds=120)
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        
        value = await fetch_func()
        if value is not None:  # Only cache non-None values
            await self.set(key, value, ttl_seconds)
        return value
    
    async def clear(self):
        """Clear all cached values"""
        async with self._lock:
            self._cache.clear()
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache size and entry details
        """
        async with self._lock:
            now = datetime.utcnow()
            return {
                "total_entries": len(self._cache),
                "active_entries": sum(1 for _, expiry in self._cache.values() if now < expiry),
                "expired_entries": sum(1 for _, expiry in self._cache.values() if now >= expiry)
            }


# Global cache instance
# Recommended TTL values:
# - SoloPool stats: 120 seconds (2 minutes)
# - CKPool stats: 60 seconds (1 minute)
# - Block explorer data: 300 seconds (5 minutes)
api_cache = SimpleCache()
