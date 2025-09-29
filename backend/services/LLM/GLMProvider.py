"""
GLM 4.5 API Provider for cloud-based LLM inference
"""

import asyncio
import aiohttp
import json
import time
import logging
from typing import Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GLMConfig:
    """Configuration for GLM 4.5 API"""
    api_key: str
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    model: str = "glm-4-0520"
    max_tokens: int = 4096
    temperature: float = 0.8
    top_p: float = 0.95
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


class GLMProvider:
    """
    GLM 4.5 API Provider with streaming support, rate limiting, and error handling
    """
    
    def __init__(self, config: GLMConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_count = 0
        self.rate_limit_window = 60  # 1 minute
        self.max_requests_per_minute = 200
        self.request_timestamps: List[float] = []
        self.usage_stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "errors": 0,
            "last_request_time": None
        }
        
    async def __aenter__(self):
        await self._ensure_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session is available"""
        if not self.session or self.session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AI-VTuber-Nex-Aris/1.0"
                }
            )
            
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
            
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits"""
        now = time.time()
        # Remove timestamps older than rate limit window
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if now - ts < self.rate_limit_window
        ]
        
        return len(self.request_timestamps) < self.max_requests_per_minute
    
    def _add_request_timestamp(self):
        """Add current timestamp to request tracking"""
        self.request_timestamps.append(time.time())
        self.request_count += 1
        self.usage_stats["total_requests"] += 1
        self.usage_stats["last_request_time"] = time.time()
    
    def _format_messages(self, text: str, history: List[Dict], system_prompt: str) -> List[Dict]:
        """Format messages for GLM API"""
        messages = []
        
        # Add system prompt
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        # Add conversation history
        for msg in history[-10:]:  # Limit to last 10 messages to manage context
            if msg.get("role") in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # Add current user message
        messages.append({
            "role": "user", 
            "content": text
        })
        
        return messages
    
    async def get_completion(
        self, 
        text: str, 
        history: List[Dict], 
        system_prompt: str,
        stream: bool = False,
        **kwargs
    ) -> str:
        """
        Get completion from GLM 4.5 API
        
        Args:
            text: User input text
            history: Conversation history
            system_prompt: System prompt
            stream: Whether to use streaming
            **kwargs: Additional parameters
            
        Returns:
            Generated response text
        """
        if not self._check_rate_limit():
            raise Exception("Rate limit exceeded. Please wait before making more requests.")
        
        await self._ensure_session()
        
        messages = self._format_messages(text, history, system_prompt)
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "stream": stream
        }
        
        url = f"{self.config.base_url}/chat/completions"
        
        for attempt in range(self.config.max_retries):
            try:
                self._add_request_timestamp()
                
                async with self.session.post(url, json=payload) as response:
                    if response.status == 200:
                        if stream:
                            return await self._handle_streaming_response(response)
                        else:
                            result = await response.json()
                            content = result["choices"][0]["message"]["content"]
                            
                            # Update usage stats
                            if "usage" in result:
                                self.usage_stats["total_tokens"] += result["usage"].get("total_tokens", 0)
                            
                            return content
                    elif response.status == 429:
                        # Rate limited
                        wait_time = self.config.retry_delay * (2 ** attempt)
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}")
                        await asyncio.sleep(wait_time)
                    else:
                        error_text = await response.text()
                        logger.error(f"GLM API error {response.status}: {error_text}")
                        self.usage_stats["errors"] += 1
                        
                        if attempt == self.config.max_retries - 1:
                            raise Exception(f"GLM API error {response.status}: {error_text}")
                        
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                        
            except asyncio.TimeoutError:
                logger.error(f"GLM API timeout on attempt {attempt + 1}")
                self.usage_stats["errors"] += 1
                if attempt == self.config.max_retries - 1:
                    raise Exception("GLM API request timed out")
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                
            except Exception as e:
                logger.error(f"GLM API error on attempt {attempt + 1}: {str(e)}")
                self.usage_stats["errors"] += 1
                if attempt == self.config.max_retries - 1:
                    raise e
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))
    
    async def _handle_streaming_response(self, response) -> str:
        """Handle streaming response from GLM API"""
        full_content = ""
        
        async for line in response.content:
            line_str = line.decode('utf-8').strip()
            
            if line_str.startswith('data: '):
                data_str = line_str[6:]  # Remove 'data: ' prefix
                
                if data_str == '[DONE]':
                    break
                    
                try:
                    data = json.loads(data_str)
                    if 'choices' in data and len(data['choices']) > 0:
                        delta = data['choices'][0].get('delta', {})
                        if 'content' in delta:
                            full_content += delta['content']
                except json.JSONDecodeError:
                    continue
        
        return full_content
    
    async def stream_completion(
        self, 
        text: str, 
        history: List[Dict], 
        system_prompt: str,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion from GLM 4.5 API
        
        Args:
            text: User input text
            history: Conversation history
            system_prompt: System prompt
            **kwargs: Additional parameters
            
        Yields:
            Streaming response chunks
        """
        if not self._check_rate_limit():
            raise Exception("Rate limit exceeded. Please wait before making more requests.")
        
        await self._ensure_session()
        
        messages = self._format_messages(text, history, system_prompt)
        
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "stream": True
        }
        
        url = f"{self.config.base_url}/chat/completions"
        
        self._add_request_timestamp()
        
        async with self.session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"GLM API streaming error {response.status}: {error_text}")
                self.usage_stats["errors"] += 1
                raise Exception(f"GLM API streaming error {response.status}: {error_text}")
            
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # Remove 'data: ' prefix
                    
                    if data_str == '[DONE]':
                        break
                        
                    try:
                        data = json.loads(data_str)
                        if 'choices' in data and len(data['choices']) > 0:
                            delta = data['choices'][0].get('delta', {})
                            if 'content' in delta:
                                yield delta['content']
                    except json.JSONDecodeError:
                        continue
    
    def is_available(self) -> bool:
        """Check if GLM provider is available"""
        return bool(self.config.api_key and self.config.base_url)
    
    def get_usage_stats(self) -> Dict:
        """Get usage statistics"""
        return self.usage_stats.copy()
    
    def get_rate_limit_status(self) -> Dict:
        """Get current rate limit status"""
        now = time.time()
        recent_requests = [
            ts for ts in self.request_timestamps 
            if now - ts < self.rate_limit_window
        ]
        
        return {
            "requests_in_window": len(recent_requests),
            "max_requests_per_minute": self.max_requests_per_minute,
            "window_remaining_seconds": self.rate_limit_window - (now - min(recent_requests)) if recent_requests else 0,
            "can_make_request": len(recent_requests) < self.max_requests_per_minute
        }


# Factory function for easier instantiation
def create_glm_provider(
    api_key: str,
    base_url: str = "https://open.bigmodel.cn/api/paas/v4",
    model: str = "glm-4-0520",
    **kwargs
) -> GLMProvider:
    """Create a GLM provider instance"""
    config = GLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        **kwargs
    )
    return GLMProvider(config)