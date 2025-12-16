"""
Tuning profiles API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

from core.database import get_db, TuningProfile, Miner, Event
from adapters import create_adapter


router = APIRouter()


class TuningProfileCreate(BaseModel):
    name: str
    miner_type: str
    description: Optional[str] = None
    settings: Dict


class TuningProfileResponse(BaseModel):
    id: int
    name: str
    miner_type: str
    description: Optional[str]
    settings: Dict
    is_system: bool
    created_at: datetime


@router.get("/profiles", response_model=list[TuningProfileResponse])
async def list_profiles(
    miner_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all tuning profiles, optionally filtered by miner type"""
    query = select(TuningProfile)
    if miner_type:
        query = query.where(TuningProfile.miner_type == miner_type)
    query = query.order_by(TuningProfile.is_system.desc(), TuningProfile.name)
    
    result = await db.execute(query)
    profiles = result.scalars().all()
    
    return [
        TuningProfileResponse(
            id=p.id,
            name=p.name,
            miner_type=p.miner_type,
            description=p.description,
            settings=p.settings,
            is_system=p.is_system,
            created_at=p.created_at
        )
        for p in profiles
    ]


@router.get("/profiles/{profile_id}", response_model=TuningProfileResponse)
async def get_profile(profile_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific tuning profile"""
    result = await db.execute(select(TuningProfile).where(TuningProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return TuningProfileResponse(
        id=profile.id,
        name=profile.name,
        miner_type=profile.miner_type,
        description=profile.description,
        settings=profile.settings,
        is_system=profile.is_system,
        created_at=profile.created_at
    )


@router.post("/profiles", response_model=TuningProfileResponse)
async def create_profile(
    profile: TuningProfileCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new tuning profile"""
    db_profile = TuningProfile(
        name=profile.name,
        miner_type=profile.miner_type,
        description=profile.description,
        settings=profile.settings,
        is_system=False
    )
    
    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    
    # Log event
    event = Event(
        event_type="info",
        message=f"Created tuning profile: {profile.name} for {profile.miner_type}"
    )
    db.add(event)
    await db.commit()
    
    return TuningProfileResponse(
        id=db_profile.id,
        name=db_profile.name,
        miner_type=db_profile.miner_type,
        description=db_profile.description,
        settings=db_profile.settings,
        is_system=db_profile.is_system,
        created_at=db_profile.created_at
    )


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a tuning profile"""
    result = await db.execute(select(TuningProfile).where(TuningProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    if profile.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system profiles")
    
    await db.delete(profile)
    await db.commit()
    
    # Log event
    event = Event(
        event_type="info",
        message=f"Deleted tuning profile: {profile.name}"
    )
    db.add(event)
    await db.commit()
    
    return {"message": "Profile deleted successfully"}


@router.post("/profiles/{profile_id}/apply/{miner_id}")
async def apply_profile(
    profile_id: int,
    miner_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Apply a tuning profile to a miner"""
    # Get profile
    result = await db.execute(select(TuningProfile).where(TuningProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    # Get miner
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Verify miner type matches profile
    if miner.miner_type != profile.miner_type:
        raise HTTPException(
            status_code=400,
            detail=f"Profile is for {profile.miner_type} but miner is {miner.miner_type}"
        )
    
    # Create adapter
    adapter = create_adapter(
        miner.miner_type,
        miner.id,
        miner.name,
        miner.ip_address,
        miner.port,
        miner.config
    )
    
    if not adapter:
        raise HTTPException(status_code=500, detail="Failed to create miner adapter")
    
    # Apply settings based on miner type
    success = False
    if miner.miner_type in ["bitaxe", "nerdqaxe"]:
        # For Bitaxe/NerdQaxe, send frequency and voltage
        success = await adapter._apply_custom_settings(profile.settings)
    elif miner.miner_type == "avalon_nano":
        # For Avalon, set mode if specified
        if "mode" in profile.settings:
            success = await adapter.set_mode(profile.settings["mode"])
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to apply profile settings")
    
    # Log event
    event = Event(
        event_type="success",
        message=f"Applied profile '{profile.name}' to {miner.name}"
    )
    db.add(event)
    await db.commit()
    
    return {"message": f"Profile applied to {miner.name} successfully"}


@router.post("/profiles/save-current/{miner_id}")
async def save_current_settings(
    miner_id: int,
    name: str,
    description: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Save current miner settings as a new profile"""
    # Get miner
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Create adapter and get current telemetry
    adapter = create_adapter(
        miner.miner_type,
        miner.id,
        miner.name,
        miner.ip_address,
        miner.port,
        miner.config
    )
    
    if not adapter:
        raise HTTPException(status_code=500, detail="Failed to create miner adapter")
    
    telemetry = await adapter.get_telemetry()
    if not telemetry or not telemetry.extra_data:
        raise HTTPException(status_code=404, detail="Could not read current miner settings")
    
    # Extract relevant settings based on miner type
    settings = {}
    if miner.miner_type in ["bitaxe", "nerdqaxe"]:
        if "frequency" in telemetry.extra_data:
            settings["frequency"] = telemetry.extra_data["frequency"]
        if "voltage" in telemetry.extra_data:
            settings["voltage"] = telemetry.extra_data["voltage"]
    elif miner.miner_type == "avalon_nano":
        if "current_mode" in telemetry.extra_data:
            settings["mode"] = telemetry.extra_data["current_mode"]
    
    if not settings:
        raise HTTPException(status_code=400, detail="No tunable settings found for this miner type")
    
    # Create profile
    db_profile = TuningProfile(
        name=name,
        miner_type=miner.miner_type,
        description=description or f"Saved from {miner.name}",
        settings=settings,
        is_system=False
    )
    
    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    
    # Log event
    event = Event(
        event_type="info",
        message=f"Saved current settings from {miner.name} as profile '{name}'"
    )
    db.add(event)
    await db.commit()
    
    return TuningProfileResponse(
        id=db_profile.id,
        name=db_profile.name,
        miner_type=db_profile.miner_type,
        description=db_profile.description,
        settings=db_profile.settings,
        is_system=db_profile.is_system,
        created_at=db_profile.created_at
    )
