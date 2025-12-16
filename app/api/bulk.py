"""
Bulk operations API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

from core.database import get_db, Miner, Pool, Event
from adapters import create_adapter


router = APIRouter()


class BulkOperationRequest(BaseModel):
    miner_ids: List[int]
    operation: str  # enable, disable, set_mode, switch_pool, restart, apply_profile
    params: Optional[Dict] = None


class BulkOperationResult(BaseModel):
    miner_id: int
    miner_name: str
    success: bool
    message: str


class BulkOperationResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: List[BulkOperationResult]


@router.post("/execute", response_model=BulkOperationResponse)
async def execute_bulk_operation(
    request: BulkOperationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Execute a bulk operation on multiple miners"""
    
    if not request.miner_ids:
        raise HTTPException(status_code=400, detail="No miner IDs provided")
    
    # Get all requested miners
    result = await db.execute(
        select(Miner).where(Miner.id.in_(request.miner_ids))
    )
    miners = result.scalars().all()
    
    if not miners:
        raise HTTPException(status_code=404, detail="No miners found with provided IDs")
    
    results = []
    successful = 0
    failed = 0
    
    for miner in miners:
        try:
            success = False
            message = ""
            
            if request.operation == "enable":
                miner.enabled = True
                success = True
                message = "Miner enabled"
                
            elif request.operation == "disable":
                miner.enabled = False
                success = True
                message = "Miner disabled"
                
            elif request.operation == "set_mode":
                if not request.params or "mode" not in request.params:
                    raise ValueError("Mode parameter required")
                
                adapter = create_adapter(
                    miner.miner_type,
                    miner.id,
                    miner.name,
                    miner.ip_address,
                    miner.port,
                    miner.config
                )
                
                if adapter:
                    success = await adapter.set_mode(request.params["mode"])
                    message = f"Mode set to {request.params['mode']}" if success else "Failed to set mode"
                else:
                    message = "Failed to create adapter"
                    
            elif request.operation == "switch_pool":
                if not request.params or "pool_id" not in request.params:
                    raise ValueError("Pool ID parameter required")
                
                # Get pool details
                pool_result = await db.execute(
                    select(Pool).where(Pool.id == request.params["pool_id"])
                )
                pool = pool_result.scalar_one_or_none()
                
                if not pool:
                    raise ValueError(f"Pool {request.params['pool_id']} not found")
                
                adapter = create_adapter(
                    miner.miner_type,
                    miner.id,
                    miner.name,
                    miner.ip_address,
                    miner.port,
                    miner.config
                )
                
                if adapter:
                    success = await adapter.switch_pool(
                        pool.url,
                        pool.port,
                        pool.user,
                        pool.password
                    )
                    message = f"Switched to pool {pool.name}" if success else "Failed to switch pool"
                else:
                    message = "Failed to create adapter"
                    
            elif request.operation == "restart":
                adapter = create_adapter(
                    miner.miner_type,
                    miner.id,
                    miner.name,
                    miner.ip_address,
                    miner.port,
                    miner.config
                )
                
                if adapter and hasattr(adapter, 'restart'):
                    success = await adapter.restart()
                    message = "Miner restarted" if success else "Failed to restart"
                else:
                    message = "Restart not supported for this miner type"
                    
            elif request.operation == "apply_profile":
                if not request.params or "profile_id" not in request.params:
                    raise ValueError("Profile ID parameter required")
                
                # Import here to avoid circular dependency
                from core.database import TuningProfile
                
                profile_result = await db.execute(
                    select(TuningProfile).where(TuningProfile.id == request.params["profile_id"])
                )
                profile = profile_result.scalar_one_or_none()
                
                if not profile:
                    raise ValueError(f"Profile {request.params['profile_id']} not found")
                
                if miner.miner_type != profile.miner_type:
                    message = f"Profile is for {profile.miner_type}, miner is {miner.miner_type}"
                    success = False
                else:
                    adapter = create_adapter(
                        miner.miner_type,
                        miner.id,
                        miner.name,
                        miner.ip_address,
                        miner.port,
                        miner.config
                    )
                    
                    if adapter:
                        if miner.miner_type in ["bitaxe", "nerdqaxe"] and hasattr(adapter, '_apply_custom_settings'):
                            success = await adapter._apply_custom_settings(profile.settings)
                        elif miner.miner_type == "avalon_nano" and "mode" in profile.settings:
                            success = await adapter.set_mode(profile.settings["mode"])
                        
                        message = f"Applied profile {profile.name}" if success else "Failed to apply profile"
                    else:
                        message = "Failed to create adapter"
            else:
                raise ValueError(f"Unknown operation: {request.operation}")
            
            if success:
                successful += 1
            else:
                failed += 1
                
            results.append(BulkOperationResult(
                miner_id=miner.id,
                miner_name=miner.name,
                success=success,
                message=message
            ))
            
        except Exception as e:
            failed += 1
            results.append(BulkOperationResult(
                miner_id=miner.id,
                miner_name=miner.name,
                success=False,
                message=str(e)
            ))
    
    # Commit database changes (for enable/disable operations)
    await db.commit()
    
    # Log event
    event = Event(
        event_type="info" if failed == 0 else "warning",
        message=f"Bulk operation '{request.operation}' completed: {successful} successful, {failed} failed"
    )
    db.add(event)
    await db.commit()
    
    return BulkOperationResponse(
        total=len(results),
        successful=successful,
        failed=failed,
        results=results
    )
