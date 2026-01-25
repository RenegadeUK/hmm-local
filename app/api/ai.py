"""
API endpoints for Sam - AI Mining Assistant
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
import json

from core.ai_assistant import SamAssistant
from core.config import app_config

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    conversation_history: Optional[List[Dict]] = []


class OpenAIConfig(BaseModel):
    """OpenAI/Ollama configuration model"""
    enabled: bool
    provider: str = "openai"  # "openai" or "ollama"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-4o"
    max_tokens: int = 1000


@router.get("/status")
async def get_ai_status():
    """Get Sam's configuration status"""
    config = app_config.get("openai", {})
    enabled = config.get("enabled", False)  # Default to False if not set
    provider = config.get("provider", "openai")
    has_key = bool(config.get("api_key"))
    
    result = {
        "enabled": enabled,
        "configured": False,
        "model": config.get("model", "gpt-4o"),
        "provider": provider,
        "config": {
            "enabled": enabled,
            "provider": provider,
            "model": config.get("model", "gpt-4o"),
            "max_tokens": config.get("max_tokens", 1000),
            "base_url": config.get("base_url")
        }
    }
    
    # For Ollama, we don't need an API key
    if not enabled or (provider == "openai" and not has_key):
        result["error"] = "Sam is not configured" if not has_key else "Sam is disabled"
        result["configured"] = False
        return result
    
    # Test connection
    sam = SamAssistant()
    test_result = await sam.test_connection()
    
    result["configured"] = test_result["success"]
    result["error"] = test_result.get("error") if not test_result["success"] else None
    
    return result


@router.post("/chat")
async def chat_with_sam(chat_message: ChatMessage):
    """
    Chat with Sam (streaming response)
    
    Request body:
    {
        "message": "Which miner is most profitable?",
        "conversation_history": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi! I'm Sam..."}
        ]
    }
    """
    sam = SamAssistant()
    
    if not sam.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Sam is not configured. Please add an OpenAI API key in Settings > Integrations."
        )
    
    async def generate():
        """Generate streaming response in SSE format"""
        try:
            async for chunk in sam.chat(
                chat_message.message,
                chat_message.conversation_history
            ):
                # Format as Server-Sent Events
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            
            # Send done signal
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Sam streaming error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/config")
async def save_openai_config(config: OpenAIConfig):
    """Save OpenAI/Ollama configuration"""
    try:
        # Update config
        openai_config = {
            "enabled": config.enabled,
            "provider": config.provider,
            "model": config.model,
            "max_tokens": config.max_tokens
        }
        
        # Add base_url if provided
        if config.base_url:
            openai_config["base_url"] = config.base_url
        
        # Only update API key if provided (or keep existing)
        if config.api_key:
            # TODO: Encrypt API key before storing
            openai_config["api_key"] = config.api_key
        elif "openai" in app_config and "api_key" in app_config["openai"]:
            # Keep existing key
            openai_config["api_key"] = app_config["openai"]["api_key"]
        
        app_config["openai"] = openai_config
        app_config.save()
        
        # Test connection if enabled
        if config.enabled:
            # For Ollama, we don't need an API key
            # For OpenAI, we need an API key
            if config.provider == "ollama" or openai_config.get("api_key"):
                sam = SamAssistant()
                test_result = await sam.test_connection()
                
                if not test_result["success"]:
                    return {
                        "success": False,
                        "error": f"Configuration saved but connection test failed: {test_result.get('error')}"
                    }
        
        return {"success": True}
    
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_openai_connection():
    """Test OpenAI API connection"""
    sam = SamAssistant()
    
    if not sam.is_enabled():
        return {
            "success": False,
            "error": "Sam is not configured"
        }
    
    result = await sam.test_connection()
    return result
