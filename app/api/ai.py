"""
API endpoints for AI Assistant configuration
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

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


@router.post("/config")
async def save_ai_config(config: AIConfig):
    """Save AI configuration"""
    try:
        # Update config
        ai_config = {
            "enabled": config.enabled,
            "provider": config.provider,
            "model": config.model,
            "max_tokens": config.max_tokens
        }
        
        # Add base_url if provided
        if config.base_url:
            ai_config["base_url"] = config.base_url
        
        # Only update API key if provided (not masked placeholder)
        if config.api_key and config.api_key != "●●●●●●●●●●●●●●●●":
            ai_config["api_key"] = config.api_key
        elif "openai" in app_config and "api_key" in app_config["openai"]:
            # Keep existing key
            ai_config["api_key"] = app_config["openai"]["api_key"]
        
        app_config["openai"] = ai_config
        app_config.save()
        
        return {"success": True}
    
    except Exception as e:
        logger.error(f"Failed to save AI config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
