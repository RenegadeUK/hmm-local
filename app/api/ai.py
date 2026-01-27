"""
API endpoints for AI Assistant configuration
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
import httpx

from core.config import app_config

router = APIRouter()
logger = logging.getLogger(__name__)


class AIConfig(BaseModel):
    """AI configuration model"""
    enabled: bool
    provider: str = "openai"  # "openai" or "ollama"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-4o"
    max_tokens: int = 1000


class AITestRequest(BaseModel):
    """AI test connection request"""
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str


@router.get("/config")
async def get_ai_config():
    """Get current AI configuration"""
    config = app_config.get("openai", {})
    
    return {
        "enabled": config.get("enabled", False),
        "provider": config.get("provider", "openai"),
        "model": config.get("model", "gpt-4o"),
        "max_tokens": config.get("max_tokens", 1000),
        "base_url": config.get("base_url"),
        "api_key": "●●●●●●●●●●●●●●●●" if config.get("api_key") else None
    }


@router.get("/status")
async def get_ai_status():
    """Get AI configuration status"""
    config = app_config.get("openai", {})
    enabled = config.get("enabled", False)
    provider = config.get("provider", "openai")
    has_key = bool(config.get("api_key"))
    
    return {
        "enabled": enabled,
        "configured": has_key if provider == "openai" else bool(config.get("base_url")),
        "provider": provider,
        "config": {
            "enabled": enabled,
            "provider": provider,
            "model": config.get("model", "gpt-4o"),
            "max_tokens": config.get("max_tokens", 1000),
            "base_url": config.get("base_url")
        }
    }


@router.post("/config")
async def save_ai_config(config: AIConfig):
    """Save AI configuration"""
    try:
        # Update config
        ai_config = {
            "enabled": bool(config.enabled),
            "provider": str(config.provider),
            "model": str(config.model),
            "max_tokens": int(config.max_tokens)
        }
        
        # Add base_url if provided
        if config.base_url:
            ai_config["base_url"] = str(config.base_url)
        
        # Only update API key if provided (not masked placeholder)
        if config.api_key and config.api_key != "●●●●●●●●●●●●●●●●":
            ai_config["api_key"] = str(config.api_key)
        else:
            # Keep existing key if present
            existing_config = app_config.get("openai", {})
            if isinstance(existing_config, dict) and "api_key" in existing_config:
                ai_config["api_key"] = str(existing_config["api_key"])
        
        app_config["openai"] = ai_config
        app_config.save()
        
        return {"success": True}
    
    except Exception as e:
        import traceback
        logger.error(f"Failed to save AI config: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_ai_connection(request: AITestRequest):
    """Test AI connection (OpenAI or Ollama)"""
    try:
        if request.provider == "openai":
            # Test OpenAI API
            if not request.api_key:
                return {"success": False, "error": "API key is required"}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{request.base_url or 'https://api.openai.com/v1'}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {request.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": request.model,
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 5
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "model": data.get("model", request.model),
                        "message": f"Connected! Using model: {request.model}"
                    }
                else:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get("error", {}).get("message", response.text or "Unknown error")
                    return {"success": False, "error": error_msg}
        
        elif request.provider == "ollama":
            # Test Ollama connection and check if model exists
            base_url = request.base_url or "http://localhost:11434"
            # Remove /v1 suffix if present
            base_url = base_url.rstrip("/v1").rstrip("/")
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                # First, check if Ollama is reachable
                try:
                    response = await client.get(f"{base_url}/api/tags")
                    
                    if response.status_code != 200:
                        return {
                            "success": False,
                            "error": f"Cannot reach Ollama at {base_url}. Status: {response.status_code}"
                        }
                    
                    # Check if model exists
                    data = response.json()
                    models = data.get("models", [])
                    model_names = [m.get("name") for m in models]
                    
                    if request.model in model_names:
                        return {
                            "success": True,
                            "message": f"Connected! Model '{request.model}' is available."
                        }
                    else:
                        available = ", ".join(model_names[:5]) if model_names else "none"
                        return {
                            "success": False,
                            "error": f"Model '{request.model}' not found. Available: {available}. Run: ollama pull {request.model}"
                        }
                
                except httpx.ConnectError:
                    return {
                        "success": False,
                        "error": f"Cannot connect to Ollama at {base_url}. Is Ollama running?"
                    }
        
        else:
            return {"success": False, "error": f"Unknown provider: {request.provider}"}
    
    except Exception as e:
        logger.error(f"AI test error: {e}")
        return {"success": False, "error": str(e)}
