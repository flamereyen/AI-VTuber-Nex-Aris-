import asyncio
from services.lib.LAV_logger import logger

from .GPTsovits.GptSovits import GptSovits

class TTS:
    def __init__(self):
        self.tts_engine = GptSovits()
        self.current_voice = "leaf"

    def get_available_voices(self):
        """Get list of available voices from the models directory"""
        return self.tts_engine.get_available_voices()

    def change_voice(self, voice_name):
        """Change the current voice to the specified one"""
        return self.tts_engine.change_voice(voice_name)

    async def synthesize_async(self, text, use_cloud=True):
        """
        Async version of synthesize with cloud provider integration
        
        Args:
            text: Text to synthesize
            use_cloud: Whether to try cloud providers first
            
        Returns:
            Audio data (bytes or file-like object)
        """
        try:
            # Try cloud provider first if enabled
            if use_cloud:
                try:
                    from ..CloudManager import cloud_manager
                    
                    async def local_fallback(text, voice_id, **kwargs):
                        return self.synthesize(text)
                    
                    response = await cloud_manager.get_tts_synthesis(
                        text=text,
                        voice_id=None,  # Use default voice
                        use_cloud=use_cloud,
                        fallback_callback=local_fallback
                    )
                    return response
                except Exception as e:
                    logger.warning(f"Cloud TTS failed, falling back to local: {e}")
            
            # Fallback to local processing
            return self.synthesize(text)
            
        except Exception as e:
            logger.error(f"Error in async synthesis: {e}")
            raise e

    def synthesize(self, text):
        """Synthesize text to speech using the current voice"""
        return self.tts_engine.synthesize(text)
    
    def upload_voice(self, name, reference_audio, reference_text, reference_language):
        return self.tts_engine.upload_voice(name, reference_audio, reference_text, reference_language)
    
    def delete_voice(self, name):
        return self.tts_engine.delete_voice(name)
    