"""
ElevenLabs TTS Provider for high-quality cloud voice synthesis
"""

import asyncio
import aiohttp
import json
import io
import time
import logging
from typing import Dict, List, Optional, AsyncGenerator, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AudioFormat(Enum):
    """Supported audio formats"""
    MP3_44100_128 = "mp3_44100_128"
    MP3_22050_32 = "mp3_22050_32"
    PCM_16000 = "pcm_16000"
    PCM_22050 = "pcm_22050"
    PCM_24000 = "pcm_24000"
    PCM_44100 = "pcm_44100"


@dataclass
class ElevenLabsConfig:
    """Configuration for ElevenLabs API"""
    api_key: str
    base_url: str = "https://api.elevenlabs.io/v1"
    default_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
    model_id: str = "eleven_monolingual_v1"
    optimize_streaming_latency: int = 1
    output_format: AudioFormat = AudioFormat.PCM_44100
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


class ElevenLabsProvider:
    """
    ElevenLabs TTS Provider with streaming support, voice cloning, and error handling
    """
    
    def __init__(self, config: ElevenLabsConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.available_voices: Dict[str, Dict] = {}
        self.usage_stats = {
            "total_requests": 0,
            "total_characters": 0,
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
                limit=50,
                limit_per_host=20,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "xi-api-key": self.config.api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "AI-VTuber-Nex-Aris/1.0"
                }
            )
            
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_available_voices(self) -> Dict[str, Dict]:
        """Get list of available voices"""
        await self._ensure_session()
        
        url = f"{self.config.base_url}/voices"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    voices = {}
                    for voice in data.get("voices", []):
                        voices[voice["voice_id"]] = {
                            "name": voice["name"],
                            "category": voice.get("category", "premade"),
                            "accent": voice.get("labels", {}).get("accent", ""),
                            "description": voice.get("labels", {}).get("description", ""),
                            "age": voice.get("labels", {}).get("age", ""),
                            "gender": voice.get("labels", {}).get("gender", ""),
                            "use_case": voice.get("labels", {}).get("use case", "")
                        }
                    self.available_voices = voices
                    return voices
                else:
                    error_text = await response.text()
                    logger.error(f"ElevenLabs voices API error {response.status}: {error_text}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching voices: {str(e)}")
            return {}
    
    async def synthesize_text(
        self,
        text: str,
        voice_id: Optional[str] = None,
        voice_settings: Optional[Dict] = None,
        model_id: Optional[str] = None,
        output_format: Optional[AudioFormat] = None
    ) -> bytes:
        """
        Synthesize text to speech
        
        Args:
            text: Text to synthesize
            voice_id: Voice ID to use (defaults to config default)
            voice_settings: Voice settings (stability, similarity_boost, style, use_speaker_boost)
            model_id: Model ID to use
            output_format: Output audio format
            
        Returns:
            Audio data as bytes
        """
        await self._ensure_session()
        
        voice_id = voice_id or self.config.default_voice_id
        model_id = model_id or self.config.model_id
        output_format = output_format or self.config.output_format
        
        # Default voice settings
        if voice_settings is None:
            voice_settings = {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings
        }
        
        url = f"{self.config.base_url}/text-to-speech/{voice_id}"
        
        # Add output format to URL parameters
        params = {"output_format": output_format.value}
        
        for attempt in range(self.config.max_retries):
            try:
                self.usage_stats["total_requests"] += 1
                self.usage_stats["total_characters"] += len(text)
                self.usage_stats["last_request_time"] = time.time()
                
                async with self.session.post(url, json=payload, params=params) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        return audio_data
                    elif response.status == 429:
                        # Rate limited
                        wait_time = self.config.retry_delay * (2 ** attempt)
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}")
                        await asyncio.sleep(wait_time)
                    else:
                        error_text = await response.text()
                        logger.error(f"ElevenLabs TTS error {response.status}: {error_text}")
                        self.usage_stats["errors"] += 1
                        
                        if attempt == self.config.max_retries - 1:
                            raise Exception(f"ElevenLabs TTS error {response.status}: {error_text}")
                        
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                        
            except asyncio.TimeoutError:
                logger.error(f"ElevenLabs TTS timeout on attempt {attempt + 1}")
                self.usage_stats["errors"] += 1
                if attempt == self.config.max_retries - 1:
                    raise Exception("ElevenLabs TTS request timed out")
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                
            except Exception as e:
                logger.error(f"ElevenLabs TTS error on attempt {attempt + 1}: {str(e)}")
                self.usage_stats["errors"] += 1
                if attempt == self.config.max_retries - 1:
                    raise e
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        
        raise Exception("Max retries exceeded")
    
    async def stream_synthesize_text(
        self,
        text: str,
        voice_id: Optional[str] = None,
        voice_settings: Optional[Dict] = None,
        model_id: Optional[str] = None,
        output_format: Optional[AudioFormat] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream synthesize text to speech
        
        Args:
            text: Text to synthesize
            voice_id: Voice ID to use
            voice_settings: Voice settings
            model_id: Model ID to use
            output_format: Output audio format
            
        Yields:
            Audio chunks as bytes
        """
        await self._ensure_session()
        
        voice_id = voice_id or self.config.default_voice_id
        model_id = model_id or self.config.model_id
        output_format = output_format or self.config.output_format
        
        if voice_settings is None:
            voice_settings = {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings
        }
        
        url = f"{self.config.base_url}/text-to-speech/{voice_id}/stream"
        
        params = {
            "output_format": output_format.value,
            "optimize_streaming_latency": self.config.optimize_streaming_latency
        }
        
        self.usage_stats["total_requests"] += 1
        self.usage_stats["total_characters"] += len(text)
        self.usage_stats["last_request_time"] = time.time()
        
        try:
            async with self.session.post(url, json=payload, params=params) as response:
                if response.status == 200:
                    async for chunk in response.content.iter_chunked(1024):
                        if chunk:
                            yield chunk
                else:
                    error_text = await response.text()
                    logger.error(f"ElevenLabs streaming error {response.status}: {error_text}")
                    self.usage_stats["errors"] += 1
                    raise Exception(f"ElevenLabs streaming error {response.status}: {error_text}")
        except Exception as e:
            logger.error(f"ElevenLabs streaming error: {str(e)}")
            self.usage_stats["errors"] += 1
            raise e
    
    async def clone_voice(
        self,
        name: str,
        files: List[bytes],
        description: Optional[str] = None,
        labels: Optional[Dict] = None
    ) -> str:
        """
        Clone a voice from audio samples
        
        Args:
            name: Name for the cloned voice
            files: List of audio file data (bytes)
            description: Description of the voice
            labels: Voice labels (accent, age, gender, etc.)
            
        Returns:
            Voice ID of the cloned voice
        """
        await self._ensure_session()
        
        url = f"{self.config.base_url}/voices/add"
        
        # Prepare multipart data
        data = aiohttp.FormData()
        data.add_field('name', name)
        
        if description:
            data.add_field('description', description)
        
        if labels:
            data.add_field('labels', json.dumps(labels))
        
        # Add audio files
        for i, file_data in enumerate(files):
            data.add_field(
                'files',
                io.BytesIO(file_data),
                filename=f'sample_{i}.wav',
                content_type='audio/wav'
            )
        
        try:
            # Remove default Content-Type header for multipart
            headers = {key: value for key, value in self.session.headers.items() 
                      if key.lower() != 'content-type'}
            
            async with self.session.post(url, data=data, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    voice_id = result.get("voice_id")
                    logger.info(f"Successfully cloned voice '{name}' with ID: {voice_id}")
                    return voice_id
                else:
                    error_text = await response.text()
                    logger.error(f"Voice cloning error {response.status}: {error_text}")
                    raise Exception(f"Voice cloning error {response.status}: {error_text}")
        except Exception as e:
            self.usage_stats["errors"] += 1
            logger.error(f"Voice cloning error: {str(e)}")
            raise e
    
    async def delete_voice(self, voice_id: str) -> bool:
        """
        Delete a cloned voice
        
        Args:
            voice_id: Voice ID to delete
            
        Returns:
            True if successful
        """
        await self._ensure_session()
        
        url = f"{self.config.base_url}/voices/{voice_id}"
        
        try:
            async with self.session.delete(url) as response:
                if response.status == 200:
                    logger.info(f"Successfully deleted voice ID: {voice_id}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Voice deletion error {response.status}: {error_text}")
                    return False
        except Exception as e:
            logger.error(f"Voice deletion error: {str(e)}")
            return False
    
    async def get_user_info(self) -> Dict:
        """Get user subscription and usage information"""
        await self._ensure_session()
        
        url = f"{self.config.base_url}/user"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"User info error {response.status}: {error_text}")
                    return {}
        except Exception as e:
            logger.error(f"User info error: {str(e)}")
            return {}
    
    def is_available(self) -> bool:
        """Check if ElevenLabs provider is available"""
        return bool(self.config.api_key and self.config.base_url)
    
    def get_usage_stats(self) -> Dict:
        """Get usage statistics"""
        return self.usage_stats.copy()
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported audio formats"""
        return [fmt.value for fmt in AudioFormat]


# Factory function for easier instantiation
def create_elevenlabs_provider(
    api_key: str,
    base_url: str = "https://api.elevenlabs.io/v1",
    default_voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    **kwargs
) -> ElevenLabsProvider:
    """Create an ElevenLabs provider instance"""
    config = ElevenLabsConfig(
        api_key=api_key,
        base_url=base_url,
        default_voice_id=default_voice_id,
        **kwargs
    )
    return ElevenLabsProvider(config)