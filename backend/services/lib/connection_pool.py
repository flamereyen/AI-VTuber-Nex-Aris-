"""
Connection pool manager for HTTP requests and other resources
"""

import asyncio
import aiohttp
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Configuration for connection pools"""
    max_connections: int = 100
    max_connections_per_host: int = 30
    ttl_dns_cache: int = 300
    timeout: int = 30
    keepalive_timeout: int = 30
    enable_cleanup_closed: bool = True


class ConnectionPoolManager:
    """
    Manages HTTP connection pools for optimal performance
    """
    
    def __init__(self, config: Optional[PoolConfig] = None):
        self.config = config or PoolConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._created_at = time.time()
        self._request_count = 0
        self._connection_stats = {
            "total_requests": 0,
            "active_connections": 0,
            "pool_created_at": self._created_at
        }
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with connection pooling"""
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    await self._create_session()
        
        return self._session
    
    async def _create_session(self):
        """Create new HTTP session with optimized settings"""
        # Create connector with connection pooling
        connector = aiohttp.TCPConnector(
            limit=self.config.max_connections,
            limit_per_host=self.config.max_connections_per_host,
            ttl_dns_cache=self.config.ttl_dns_cache,
            keepalive_timeout=self.config.keepalive_timeout,
            enable_cleanup_closed=self.config.enable_cleanup_closed,
            use_dns_cache=True,
        )
        
        # Create timeout configuration
        timeout = aiohttp.ClientTimeout(
            total=self.config.timeout,
            connect=10,
            sock_read=self.config.timeout
        )
        
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": "AI-VTuber-Nex-Aris/1.0",
                "Connection": "keep-alive"
            },
            raise_for_status=False  # Handle status codes manually
        )
        
        self._created_at = time.time()
        logger.info("Created new HTTP session with connection pooling")
    
    async def request(
        self, 
        method: str, 
        url: str, 
        **kwargs
    ) -> aiohttp.ClientResponse:
        """
        Make HTTP request using connection pool
        
        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request arguments
            
        Returns:
            HTTP response
        """
        session = await self.get_session()
        self._request_count += 1
        self._connection_stats["total_requests"] += 1
        
        try:
            response = await session.request(method, url, **kwargs)
            return response
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            raise
    
    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """GET request"""
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """POST request"""
        return await self.request("POST", url, **kwargs)
    
    async def put(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """PUT request"""
        return await self.request("PUT", url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """DELETE request"""
        return await self.request("DELETE", url, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        uptime = time.time() - self._created_at
        
        stats = {
            **self._connection_stats,
            "uptime_seconds": uptime,
            "requests_per_second": self._request_count / max(uptime, 1),
            "session_active": self._session is not None and not self._session.closed
        }
        
        # Add connector stats if available
        if self._session and not self._session.closed:
            connector = self._session.connector
            if hasattr(connector, '_conns'):
                stats["active_connections"] = sum(len(conns) for conns in connector._conns.values())
                stats["total_connections"] = len(connector._conns)
        
        return stats
    
    async def close(self):
        """Close the session and clean up resources"""
        if self._session and not self._session.closed:
            await self._session.close()
            # Wait a bit for connections to close
            await asyncio.sleep(0.1)
            logger.info("Closed HTTP session and connection pool")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class ResourcePool:
    """
    Generic resource pool for managing expensive resources
    """
    
    def __init__(self, factory, max_size: int = 10, ttl: float = 300.0):
        """
        Initialize resource pool
        
        Args:
            factory: Function to create new resources  
            max_size: Maximum pool size
            ttl: Time to live for resources
        """
        self.factory = factory
        self.max_size = max_size
        self.ttl = ttl
        self._pool = []
        self._lock = asyncio.Lock()
        self._created_count = 0
        self._borrowed_count = 0
    
    async def acquire(self):
        """Acquire resource from pool"""
        async with self._lock:
            # Clean expired resources
            now = time.time()
            self._pool = [
                (resource, created_at) for resource, created_at in self._pool
                if now - created_at < self.ttl
            ]
            
            # Try to get existing resource
            if self._pool:
                resource, _ = self._pool.pop()
                self._borrowed_count += 1
                return resource
            
            # Create new resource
            resource = await self._create_resource()
            self._created_count += 1
            self._borrowed_count += 1
            return resource
    
    async def release(self, resource):
        """Release resource back to pool"""
        async with self._lock:
            if len(self._pool) < self.max_size:
                self._pool.append((resource, time.time()))
            else:
                # Pool is full - clean up resource
                await self._cleanup_resource(resource)
    
    async def _create_resource(self):
        """Create new resource using factory"""
        if asyncio.iscoroutinefunction(self.factory):
            return await self.factory()
        else:
            return self.factory()
    
    async def _cleanup_resource(self, resource):
        """Clean up resource"""
        if hasattr(resource, 'close'):
            if asyncio.iscoroutinefunction(resource.close):
                await resource.close()
            else:
                resource.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics"""
        return {
            "pool_size": len(self._pool),
            "max_size": self.max_size,
            "created_count": self._created_count,
            "borrowed_count": self._borrowed_count,
            "ttl_seconds": self.ttl
        }
    
    async def clear(self):
        """Clear all resources from pool"""
        async with self._lock:
            for resource, _ in self._pool:
                await self._cleanup_resource(resource)
            self._pool.clear()


# Global connection pool instance
http_pool = ConnectionPoolManager()


async def get_http_session() -> aiohttp.ClientSession:
    """Get global HTTP session"""
    return await http_pool.get_session()


async def cleanup_pools():
    """Clean up all connection pools"""
    await http_pool.close()