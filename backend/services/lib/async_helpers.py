"""
Async helper utilities for performance optimizations and error handling
"""

import asyncio
import functools
import time
import logging
from typing import Any, Callable, Dict, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logger = logging.getLogger(__name__)


# Thread pool for CPU-bound tasks
_cpu_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cpu-task")
_io_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="io-task")


def async_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for async functions with exponential backoff retry logic
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries
        backoff: Multiplier for delay on each retry
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {current_delay}s...")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            raise last_exception
        return wrapper
    return decorator


def async_timeout(timeout_seconds: float):
    """
    Decorator to add timeout to async functions
    
    Args:
        timeout_seconds: Timeout in seconds
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.error(f"Function {func.__name__} timed out after {timeout_seconds}s")
                raise asyncio.TimeoutError(f"{func.__name__} timed out after {timeout_seconds}s")
        return wrapper
    return decorator


def run_in_executor(executor_type: str = "io"):
    """
    Decorator to run sync functions in thread executor
    
    Args:
        executor_type: Either "cpu" or "io" 
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            executor = _cpu_executor if executor_type == "cpu" else _io_executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))
        return wrapper
    return decorator


class AsyncCache:
    """
    Simple async cache with TTL support
    """
    
    def __init__(self, default_ttl: float = 300.0, max_size: int = 1000):
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired"""
        return time.time() > entry["expires_at"]
    
    def _cleanup_expired(self):
        """Remove expired entries"""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time > entry["expires_at"]
        ]
        for key in expired_keys:
            del self._cache[key]
    
    def _evict_lru(self):
        """Evict least recently used entries"""
        if len(self._cache) <= self.max_size:
            return
            
        # Sort by access time and remove oldest
        sorted_items = sorted(
            self._cache.items(),
            key=lambda x: x[1]["accessed_at"]
        )
        
        for key, _ in sorted_items[:len(self._cache) - self.max_size]:
            del self._cache[key]
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            if self._is_expired(entry):
                del self._cache[key]
                return None
            
            # Update access time
            entry["accessed_at"] = time.time()
            return entry["value"]
    
    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set value in cache"""
        with self._lock:
            # Cleanup expired entries periodically
            if len(self._cache) > 100:
                self._cleanup_expired()
            
            # Evict LRU entries if needed
            self._evict_lru()
            
            expires_at = time.time() + (ttl or self.default_ttl)
            self._cache[key] = {
                "value": value,
                "expires_at": expires_at,
                "accessed_at": time.time()
            }
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_entries = len(self._cache)
            expired_count = sum(1 for entry in self._cache.values() if self._is_expired(entry))
            
            return {
                "total_entries": total_entries,
                "expired_entries": expired_count,
                "active_entries": total_entries - expired_count,
                "max_size": self.max_size,
                "hit_rate": getattr(self, "_hit_count", 0) / max(getattr(self, "_request_count", 1), 1)
            }


# Global cache instance
cache = AsyncCache(default_ttl=300.0, max_size=1000)


def cached(key_func: Callable = None, ttl: float = 300.0):
    """
    Decorator for caching async function results
    
    Args:
        key_func: Function to generate cache key from args/kwargs
        ttl: Time to live in seconds
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default key generation
                cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Try to get from cache
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl)
            logger.debug(f"Cached result for {func.__name__}")
            
            return result
        return wrapper
    return decorator


async def gather_with_concurrency(tasks, max_concurrency: int = 10):
    """
    Execute async tasks with limited concurrency
    
    Args:
        tasks: List of async tasks/coroutines
        max_concurrency: Maximum number of concurrent tasks
        
    Returns:
        List of results in same order as input tasks
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def run_task(task):
        async with semaphore:
            return await task
    
    # Wrap tasks with semaphore
    wrapped_tasks = [run_task(task) for task in tasks]
    
    # Execute all tasks
    return await asyncio.gather(*wrapped_tasks)


class RateLimiter:
    """
    Token bucket rate limiter for async operations
    """
    
    def __init__(self, rate: float, burst: int = 1):
        """
        Initialize rate limiter
        
        Args:
            rate: Requests per second
            burst: Maximum burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        Acquire tokens from bucket
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False otherwise
        """
        async with self._lock:
            now = time.time()
            
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    async def wait_for_tokens(self, tokens: int = 1) -> None:
        """
        Wait until tokens are available
        
        Args:
            tokens: Number of tokens needed
        """
        while not await self.acquire(tokens):
            # Calculate wait time
            wait_time = (tokens - self.tokens) / self.rate
            await asyncio.sleep(min(wait_time, 0.1))  # Cap wait time


# Cleanup function for executors
def cleanup_executors():
    """Clean up thread pool executors"""
    _cpu_executor.shutdown(wait=False)
    _io_executor.shutdown(wait=False)