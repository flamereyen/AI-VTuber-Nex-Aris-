# 🌟 AI VTuber Cloud Integration Guide

## Overview

This enhanced AI VTuber system now supports cloud-based AI providers for improved performance, scalability, and quality. The system seamlessly integrates GLM 4.5 for language processing and ElevenLabs for high-quality text-to-speech synthesis.

## ✨ Features

### 🧠 GLM 4.5 Language Model
- **Advanced Reasoning**: Superior performance for complex conversations
- **Streaming Responses**: Real-time response generation
- **Rate Limiting**: Built-in 200 requests/minute limit with token bucket
- **Automatic Fallback**: Falls back to local models if cloud unavailable

### 🗣️ ElevenLabs Text-to-Speech
- **Studio Quality**: Professional-grade voice synthesis
- **Voice Cloning**: Create custom voices from audio samples
- **Multiple Formats**: Support for various audio formats (PCM, MP3)
- **Real-time Streaming**: Low-latency audio generation

## 🔧 Configuration

### Setting Up Cloud Providers

1. **Edit Configuration File**:
   ```json
   // backend/config/cloud_providers.json
   {
     "cloud_providers": {
       "glm": {
         "enabled": true,
         "api_key": "your_glm_api_key_here",
         "base_url": "https://open.bigmodel.cn/api/paas/v4",
         "model": "glm-4-0520"
       },
       "elevenlabs": {
         "enabled": true,
         "api_key": "your_elevenlabs_api_key_here",
         "default_voice_id": "21m00Tcm4TlvDq8ikWAM"
       }
     }
   }
   ```

2. **Get API Keys**:
   - **GLM 4.5**: Visit [https://open.bigmodel.cn/](https://open.bigmodel.cn/)
   - **ElevenLabs**: Visit [https://elevenlabs.io/](https://elevenlabs.io/)

### Environment Variables (Alternative)
```bash
# GLM Configuration
GLM_API_KEY=your_glm_api_key_here
GLM_ENABLED=true

# ElevenLabs Configuration  
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_ENABLED=true
```

## 🚀 Usage

### API Endpoints

#### GLM 4.5 Completion
```bash
POST /api/cloud/llm/glm
Content-Type: application/json

{
  "text": "Hello, how are you?",
  "history": [],
  "system_prompt": "You are a helpful AI assistant.",
  "use_cloud": true
}
```

#### ElevenLabs TTS Synthesis
```bash
POST /api/cloud/tts/elevenlabs
Content-Type: application/json

{
  "text": "Hello world!",
  "voice_id": "21m00Tcm4TlvDq8ikWAM",
  "use_cloud": true
}
```

#### Provider Status Check
```bash
GET /api/cloud/status

Response:
{
  "providers": {
    "glm": {
      "status": "available",
      "enabled": true,
      "usage_stats": {
        "total_requests": 150,
        "total_tokens": 45000,
        "errors": 2
      }
    },
    "elevenlabs": {
      "status": "available", 
      "enabled": true,
      "usage_stats": {
        "total_requests": 75,
        "total_characters": 12000,
        "errors": 0
      }
    }
  }
}
```

### Programmatic Usage

#### Python Backend
```python
from services.CloudManager import cloud_manager

# LLM Completion with fallback
async def get_ai_response(text, history, system_prompt):
    async def local_fallback(text, history, system_prompt):
        return llm.get_completion(text, history, system_prompt)
    
    response = await cloud_manager.get_llm_completion(
        text=text,
        history=history,
        system_prompt=system_prompt,
        use_cloud=True,
        fallback_callback=local_fallback
    )
    return response

# TTS Synthesis with fallback
async def synthesize_speech(text):
    async def local_fallback(text, voice_id):
        return tts.synthesize(text)
    
    audio_data = await cloud_manager.get_tts_synthesis(
        text=text,
        use_cloud=True,
        fallback_callback=local_fallback
    )
    return audio_data
```

#### JavaScript Frontend
```javascript
// GLM 4.5 Request
const response = await fetch('/api/cloud/llm/glm', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    text: 'Tell me a story',
    history: [],
    system_prompt: 'You are a creative storyteller.',
    use_cloud: true
  })
});

const data = await response.json();
console.log(data.response);

// ElevenLabs TTS Request
const audioResponse = await fetch('/api/cloud/tts/elevenlabs', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    text: 'Hello from the cloud!',
    use_cloud: true
  })
});

const audioBlob = await audioResponse.blob();
const audio = new Audio(URL.createObjectURL(audioBlob));
audio.play();
```

## 🎛️ Performance Features

### Connection Pooling
- **HTTP Reuse**: Connections are pooled and reused for efficiency
- **DNS Caching**: 300-second TTL for DNS lookups
- **Keep-Alive**: 30-second connection timeout optimization

### Error Handling
- **Exponential Backoff**: Automatic retry with increasing delays
- **Circuit Breaker**: Fails fast when services are down
- **Graceful Degradation**: Automatic fallback to local processing

### Rate Limiting
- **Token Bucket**: 200 requests/minute for GLM 4.5
- **Burst Handling**: Supports temporary spikes in usage
- **Queue Management**: Requests are queued when rate limited

### Caching
- **Response Caching**: API responses cached for improved speed
- **Memory Optimization**: LRU cache with TTL expiration
- **Statistics Tracking**: Cache hit rates and performance metrics

## 🎨 Sci-Fi Theme Integration

The enhanced UI features a futuristic sci-fi theme:

### Color Palette
- **Primary Background**: Pure black (`#000000`)
- **Secondary Background**: Dark gray (`#0a0a0a`)
- **Accent Colors**: Cyan (`#00FFFF`), Electric Blue (`#0066FF`), Neon Green (`#00FF00`)

### Visual Effects
- **Glassmorphism**: Translucent panels with blur effects
- **Neon Glow**: CSS box-shadow for glowing elements
- **Scanner Lines**: Animated scanning effects
- **Holographic Panels**: Gradient borders with transparency

### Typography
- **Monospace Fonts**: Consolas, Courier New for terminal feel
- **Text Glow**: CSS text-shadow for futuristic appearance
- **Uppercase Styling**: Button text in uppercase with letter spacing

## 📊 Monitoring & Analytics

### Provider Statistics
```javascript
// Get detailed provider stats
const stats = await fetch('/api/cloud/status').then(r => r.json());

console.log('GLM Usage:', stats.providers.glm.usage_stats);
console.log('ElevenLabs Usage:', stats.providers.elevenlabs.usage_stats);
```

### Performance Metrics
- **Response Times**: Average latency for cloud requests
- **Success Rates**: Percentage of successful API calls
- **Fallback Usage**: How often local fallback is used
- **Cache Hit Rates**: Efficiency of caching system

### Error Tracking
- **Request Failures**: Failed API calls with error details
- **Rate Limiting**: When rate limits are exceeded
- **Timeout Events**: Requests that exceed timeout limits
- **Fallback Triggers**: When and why fallbacks occur

## 🔒 Security Considerations

### API Key Management
- **Environment Variables**: Store keys in environment variables
- **Config File Security**: Ensure config files are not committed to version control
- **Key Rotation**: Regularly rotate API keys for security

### Network Security
- **HTTPS Only**: All cloud API calls use HTTPS encryption
- **Request Validation**: Input validation to prevent injection attacks
- **Rate Limiting**: Prevents abuse and DoS attacks

## 🚨 Troubleshooting

### Common Issues

1. **"Rate limit exceeded"**
   - Wait 1 minute before making more requests
   - Check your API usage limits with the provider

2. **"Cloud provider unavailable"**
   - System automatically falls back to local processing
   - Check provider status at `/api/cloud/status`

3. **"Invalid API key"**
   - Verify your API key in the configuration
   - Ensure the key has proper permissions

4. **"Connection timeout"**
   - Check internet connectivity
   - Provider may be experiencing issues

### Debug Mode
Enable detailed logging:
```python
import logging
logging.getLogger('services.CloudManager').setLevel(logging.DEBUG)
logging.getLogger('services.LLM.GLMProvider').setLevel(logging.DEBUG)
logging.getLogger('services.TTS.ElevenLabsProvider').setLevel(logging.DEBUG)
```

## 📝 Migration Guide

### From Local-Only Setup
1. Install new dependencies (already included)
2. Configure API keys in `cloud_providers.json`
3. Enable cloud providers by setting `"enabled": true`
4. Test with `/api/cloud/status` endpoint
5. System will automatically use cloud when available

### Rollback Plan
- Set `"enabled": false` for all cloud providers
- System will function exactly as before with local processing only
- No data loss or functionality impact

## 🌟 Best Practices

1. **Gradual Rollout**: Enable one provider at a time for testing
2. **Monitor Usage**: Keep track of API costs and usage limits
3. **Fallback Testing**: Regularly test local fallback functionality
4. **Key Security**: Never commit API keys to version control
5. **Performance Monitoring**: Track response times and error rates
6. **Caching Strategy**: Utilize caching for frequently requested content

## 📞 Support

For issues related to:
- **GLM 4.5**: Contact GLM support or check their documentation
- **ElevenLabs**: Visit ElevenLabs support portal
- **Integration Issues**: Check the application logs and status endpoints

---

*This cloud integration provides enterprise-grade AI capabilities while maintaining the flexibility and reliability of local processing. The system is designed for seamless operation whether online or offline.*