"""
Cloud Settings API endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from core.config import app_config, save_config
from core.cloud_push import init_cloud_service, get_cloud_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CloudConfig(BaseModel):
    """Cloud configuration model"""
    enabled: bool = False
    api_key: Optional[str] = None
    endpoint: str = "http://localhost:8082/ingest"
    installation_name: str = "My Home Mining Setup"
    installation_location: Optional[str] = None
    push_interval_minutes: int = Field(default=5, ge=1, le=60)


@router.get("/cloud/config")
async def get_cloud_config():
    """Get current cloud configuration"""
    cloud_config = app_config.get("cloud", {})
    
    # Mask API key (show only first 8 chars)
    api_key = cloud_config.get("api_key")
    if api_key:
        masked_key = api_key[:8] + "..." if len(api_key) > 8 else "***"
    else:
        masked_key = None
    
    return {
        "enabled": cloud_config.get("enabled", False),
        "api_key": masked_key,
        "endpoint": cloud_config.get("endpoint", "http://localhost:8082/ingest"),
        "installation_name": cloud_config.get("installation_name", "My Home Mining Setup"),
        "installation_location": cloud_config.get("installation_location"),
        "push_interval_minutes": cloud_config.get("push_interval_minutes", 5)
    }


@router.post("/cloud/config")
async def update_cloud_config(config: CloudConfig):
    """Update cloud configuration"""
    try:
        # Build config dict
        cloud_config = {
            "enabled": config.enabled,
            "api_key": config.api_key,
            "endpoint": config.endpoint.rstrip("/"),
            "installation_name": config.installation_name,
            "installation_location": config.installation_location,
            "push_interval_minutes": config.push_interval_minutes
        }
        
        # Update app config
        app_config["cloud"] = cloud_config
        save_config()
        
        # Reinitialize cloud service
        init_cloud_service(cloud_config)
        
        # Restart cloud push scheduler job if enabled
        from core.scheduler import scheduler_service
        if scheduler_service and scheduler_service.scheduler:
            # Remove existing job if present
            existing_job = scheduler_service.scheduler.get_job("push_to_cloud")
            if existing_job:
                scheduler_service.scheduler.remove_job("push_to_cloud")
            
            # Add new job if enabled
            if config.enabled:
                from apscheduler.triggers.interval import IntervalTrigger
                scheduler_service.scheduler.add_job(
                    scheduler_service._push_to_cloud,
                    IntervalTrigger(minutes=config.push_interval_minutes),
                    id="push_to_cloud",
                    name="Push telemetry to HMM Cloud"
                )
                logger.info(f"Cloud push scheduler job enabled (interval={config.push_interval_minutes}min)")
        
        return {"status": "success", "message": "Cloud configuration updated"}
        
    except Exception as e:
        logger.error(f"Failed to update cloud config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cloud/test")
async def test_cloud_connection():
    """Test connection to cloud"""
    cloud_service = get_cloud_service()
    
    if not cloud_service:
        raise HTTPException(status_code=400, detail="Cloud service not initialized")
    
    if not cloud_service.api_key or not cloud_service.endpoint:
        raise HTTPException(status_code=400, detail="Cloud API key and endpoint must be configured")
    
    result = await cloud_service.test_connection()
    
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["message"])


@router.post("/cloud/push/manual")
async def manual_cloud_push():
    """Manually trigger a cloud push"""
    from core.scheduler import scheduler_service
    
    if not scheduler_service:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")
    
    cloud_service = get_cloud_service()
    if not cloud_service or not cloud_service.enabled:
        raise HTTPException(status_code=400, detail="Cloud push is disabled")
    
    try:
        # Trigger cloud push
        await scheduler_service._push_to_cloud()
        return {"status": "success", "message": "Cloud push triggered"}
    except Exception as e:
        logger.error(f"Manual cloud push failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
