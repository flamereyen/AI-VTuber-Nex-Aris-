"""
Cloud Manager for coordinating cloud providers (GLM, ElevenLabs)
"""

import asyncio
import json
import os
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum

from .LLM.GLMProvider import GLMProvider, GLMConfig, create_glm_provider
from .TTS.ElevenLabsProvider import ElevenLabsProvider, ElevenLabsConfig, create_elevenlabs_provider, AudioFormat

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Provider status enumeration"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"


@dataclass
class CloudProviderConfig:
    """Configuration for a cloud provider"""
    enabled: bool = False
    api_key: str = ""
    base_url: str = ""
    max_retries: int = 3
    timeout: int = 30
    fallback_enabled: bool = True


class CloudManager:
    """
    Cloud Manager for handling multiple cloud providers with fallback mechanisms
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config: Dict[str, Any] = {}
        self.providers: Dict[str, Any] = {}
        self.provider_status: Dict[str, ProviderStatus] = {}
        
        # Load configuration
        self.load_config()
        
        # Initialize providers
        asyncio.create_task(self._initialize_providers())
    
    def _get_default_config_path(self) -> str:
        """Get default configuration file path"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(current_dir, "..", "config", "cloud_providers.json")
    
    def load_config(self) -> None:
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info(f"Loaded cloud provider configuration from {self.config_path}")
            else:
                # Create default configuration
                self.config = self._get_default_config()
                self.save_config()
                logger.info(f"Created default configuration at {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            self.config = self._get_default_config()
    
    def save_config(self) -> None:
        """Save configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "cloud_providers": {
                "glm": {
                    "enabled": False,
                    "api_key": "",
                    "base_url": "https://open.bigmodel.cn/api/paas/v4",
                    "model": "glm-4-0520",
                    "max_tokens": 4096,
                    "temperature": 0.8,
                    "top_p": 0.95,
                    "timeout": 30,
                    "max_retries": 3,
                    "fallback_enabled": True
                },
                "elevenlabs": {
                    "enabled": False,
                    "api_key": "",
                    "base_url": "https://api.elevenlabs.io/v1",
                    "default_voice_id": "21m00Tcm4TlvDq8ikWAM",
                    "model_id": "eleven_monolingual_v1",
                    "output_format": "pcm_44100",
                    "optimize_streaming_latency": 1,
                    "timeout": 30,
                    "max_retries": 3,
                    "fallback_enabled": True
                }
            },
            "fallback_strategy": {
                "llm_fallback_order": ["glm", "local"],
                "tts_fallback_order": ["elevenlabs", "local"],
                "retry_delay": 1.0,
                "max_fallback_attempts": 2
            }
        }
    
    async def _initialize_providers(self) -> None:
        """Initialize cloud providers based on configuration"""
        try:
            # Initialize GLM provider
            if self.config.get("cloud_providers", {}).get("glm", {}).get("enabled", False):
                glm_config = self.config["cloud_providers"]["glm"]
                if glm_config.get("api_key"):
                    try:
                        self.providers["glm"] = create_glm_provider(
                            api_key=glm_config["api_key"],
                            base_url=glm_config.get("base_url", "https://open.bigmodel.cn/api/paas/v4"),
                            model=glm_config.get("model", "glm-4-0520"),
                            max_tokens=glm_config.get("max_tokens", 4096),
                            temperature=glm_config.get("temperature", 0.8),
                            top_p=glm_config.get("top_p", 0.95),
                            timeout=glm_config.get("timeout", 30),
                            max_retries=glm_config.get("max_retries", 3)
                        )
                        self.provider_status["glm"] = ProviderStatus.AVAILABLE
                        logger.info("GLM provider initialized successfully")
                    except Exception as e:
                        logger.error(f"Failed to initialize GLM provider: {e}")
                        self.provider_status["glm"] = ProviderStatus.ERROR
                else:
                    logger.warning("GLM provider enabled but no API key provided")
                    self.provider_status["glm"] = ProviderStatus.DISABLED
            
            # Initialize ElevenLabs provider
            if self.config.get("cloud_providers", {}).get("elevenlabs", {}).get("enabled", False):
                elevenlabs_config = self.config["cloud_providers"]["elevenlabs"]
                if elevenlabs_config.get("api_key"):
                    try:
                        # Convert output_format string to AudioFormat enum
                        output_format_str = elevenlabs_config.get("output_format", "pcm_44100")
                        output_format = AudioFormat(output_format_str)
                        
                        self.providers["elevenlabs"] = create_elevenlabs_provider(
                            api_key=elevenlabs_config["api_key"],
                            base_url=elevenlabs_config.get("base_url", "https://api.elevenlabs.io/v1"),
                            default_voice_id=elevenlabs_config.get("default_voice_id", "21m00Tcm4TlvDq8ikWAM"),
                            model_id=elevenlabs_config.get("model_id", "eleven_monolingual_v1"),
                            output_format=output_format,
                            optimize_streaming_latency=elevenlabs_config.get("optimize_streaming_latency", 1),
                            timeout=elevenlabs_config.get("timeout", 30),
                            max_retries=elevenlabs_config.get("max_retries", 3)
                        )
                        self.provider_status["elevenlabs"] = ProviderStatus.AVAILABLE
                        logger.info("ElevenLabs provider initialized successfully")
                    except Exception as e:
                        logger.error(f"Failed to initialize ElevenLabs provider: {e}")
                        self.provider_status["elevenlabs"] = ProviderStatus.ERROR
                else:
                    logger.warning("ElevenLabs provider enabled but no API key provided")
                    self.provider_status["elevenlabs"] = ProviderStatus.DISABLED
                    
        except Exception as e:
            logger.error(f"Error initializing providers: {e}")
    
    async def get_llm_completion(
        self,
        text: str,
        history: List[Dict],
        system_prompt: str,
        use_cloud: bool = True,
        fallback_callback: Optional[callable] = None,
        **kwargs
    ) -> str:
        """
        Get LLM completion with fallback mechanism
        
        Args:
            text: User input text
            history: Conversation history
            system_prompt: System prompt
            use_cloud: Whether to try cloud providers first
            fallback_callback: Function to call for local fallback
            **kwargs: Additional parameters
            
        Returns:
            Generated response text
        """
        if not use_cloud or not self.providers.get("glm"):
            if fallback_callback:
                return await fallback_callback(text, history, system_prompt, **kwargs)
            else:
                raise Exception("No LLM provider available")
        
        # Try GLM provider first
        if self.provider_status.get("glm") == ProviderStatus.AVAILABLE:
            try:
                glm_provider = self.providers["glm"]
                async with glm_provider:
                    result = await glm_provider.get_completion(text, history, system_prompt, **kwargs)
                    return result
            except Exception as e:
                logger.error(f"GLM provider failed: {e}")
                self.provider_status["glm"] = ProviderStatus.ERROR
                
                # Fallback to local if enabled
                if (self.config.get("cloud_providers", {}).get("glm", {}).get("fallback_enabled", True) 
                    and fallback_callback):
                    logger.info("Falling back to local LLM")
                    return await fallback_callback(text, history, system_prompt, **kwargs)
                else:
                    raise e
        
        # If GLM is not available, try local fallback
        if fallback_callback:
            logger.info("Using local LLM (cloud provider unavailable)")
            return await fallback_callback(text, history, system_prompt, **kwargs)
        else:
            raise Exception("No available LLM provider")
    
    async def get_tts_synthesis(
        self,
        text: str,
        voice_id: Optional[str] = None,
        use_cloud: bool = True,
        fallback_callback: Optional[callable] = None,
        **kwargs
    ) -> bytes:
        """
        Get TTS synthesis with fallback mechanism
        
        Args:
            text: Text to synthesize
            voice_id: Voice ID to use
            use_cloud: Whether to try cloud providers first
            fallback_callback: Function to call for local fallback
            **kwargs: Additional parameters
            
        Returns:
            Audio data as bytes
        """
        if not use_cloud or not self.providers.get("elevenlabs"):
            if fallback_callback:
                return await fallback_callback(text, voice_id, **kwargs)
            else:
                raise Exception("No TTS provider available")
        
        # Try ElevenLabs provider first
        if self.provider_status.get("elevenlabs") == ProviderStatus.AVAILABLE:
            try:
                elevenlabs_provider = self.providers["elevenlabs"]
                async with elevenlabs_provider:
                    result = await elevenlabs_provider.synthesize_text(
                        text, voice_id=voice_id, **kwargs
                    )
                    return result
            except Exception as e:
                logger.error(f"ElevenLabs provider failed: {e}")
                self.provider_status["elevenlabs"] = ProviderStatus.ERROR
                
                # Fallback to local if enabled
                if (self.config.get("cloud_providers", {}).get("elevenlabs", {}).get("fallback_enabled", True)
                    and fallback_callback):
                    logger.info("Falling back to local TTS")
                    return await fallback_callback(text, voice_id, **kwargs)
                else:
                    raise e
        
        # If ElevenLabs is not available, try local fallback
        if fallback_callback:
            logger.info("Using local TTS (cloud provider unavailable)")
            return await fallback_callback(text, voice_id, **kwargs)
        else:
            raise Exception("No available TTS provider")
    
    def get_provider_status(self) -> Dict[str, Dict]:
        """Get status of all providers"""
        status = {}
        
        for provider_name, provider_status in self.provider_status.items():
            provider_info = {
                "status": provider_status.value,
                "enabled": self.config.get("cloud_providers", {}).get(provider_name, {}).get("enabled", False),
                "available": provider_status == ProviderStatus.AVAILABLE
            }
            
            # Add usage stats if provider is available
            if provider_name in self.providers and provider_status == ProviderStatus.AVAILABLE:
                try:
                    provider_info["usage_stats"] = self.providers[provider_name].get_usage_stats()
                    
                    # Add rate limit info for GLM
                    if provider_name == "glm" and hasattr(self.providers[provider_name], 'get_rate_limit_status'):
                        provider_info["rate_limit"] = self.providers[provider_name].get_rate_limit_status()
                        
                except Exception as e:
                    logger.error(f"Error getting stats for {provider_name}: {e}")
            
            status[provider_name] = provider_info
        
        return status
    
    def update_provider_config(self, provider_name: str, config_updates: Dict) -> bool:
        """
        Update provider configuration
        
        Args:
            provider_name: Name of the provider
            config_updates: Configuration updates
            
        Returns:
            True if successful
        """
        try:
            if provider_name not in self.config.get("cloud_providers", {}):
                logger.error(f"Unknown provider: {provider_name}")
                return False
            
            # Update configuration
            provider_config = self.config["cloud_providers"][provider_name]
            provider_config.update(config_updates)
            
            # Save configuration
            self.save_config()
            
            # Reinitialize provider if it was changed
            if config_updates.get("enabled") or config_updates.get("api_key"):
                asyncio.create_task(self._initialize_providers())
            
            logger.info(f"Updated configuration for {provider_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating provider config: {e}")
            return False
    
    def get_available_providers(self) -> Dict[str, bool]:
        """Get list of available providers"""
        return {
            name: status == ProviderStatus.AVAILABLE 
            for name, status in self.provider_status.items()
        }
    
    async def health_check(self) -> Dict[str, bool]:
        """
        Perform health check on all providers
        
        Returns:
            Dict with provider names and health status
        """
        health_status = {}
        
        # Check GLM provider
        if "glm" in self.providers:
            try:
                glm_provider = self.providers["glm"]
                health_status["glm"] = glm_provider.is_available()
                
                # Test with a simple request
                if health_status["glm"]:
                    async with glm_provider:
                        test_response = await glm_provider.get_completion(
                            "Hello", [], "You are a test assistant.", max_tokens=10
                        )
                        health_status["glm"] = bool(test_response)
                        
            except Exception as e:
                logger.error(f"GLM health check failed: {e}")
                health_status["glm"] = False
                self.provider_status["glm"] = ProviderStatus.ERROR
        
        # Check ElevenLabs provider
        if "elevenlabs" in self.providers:
            try:
                elevenlabs_provider = self.providers["elevenlabs"]
                health_status["elevenlabs"] = elevenlabs_provider.is_available()
                
                # Test with user info request (lighter than synthesis)
                if health_status["elevenlabs"]:
                    async with elevenlabs_provider:
                        user_info = await elevenlabs_provider.get_user_info()
                        health_status["elevenlabs"] = bool(user_info)
                        
            except Exception as e:
                logger.error(f"ElevenLabs health check failed: {e}")
                health_status["elevenlabs"] = False
                self.provider_status["elevenlabs"] = ProviderStatus.ERROR
        
        return health_status
    
    async def cleanup(self):
        """Clean up resources"""
        for provider in self.providers.values():
            if hasattr(provider, 'close'):
                try:
                    await provider.close()
                except Exception as e:
                    logger.error(f"Error closing provider: {e}")


# Global instance
cloud_manager = CloudManager()