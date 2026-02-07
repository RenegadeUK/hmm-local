"""
API endpoint for getting available pools based on miner selection for strategies
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from pydantic import BaseModel
import logging

from core.database import get_db, Miner, Pool, MinerPoolSlot

logger = logging.getLogger(__name__)

router = APIRouter()


class PoolOption(BaseModel):
    """Available pool for strategy"""
    id: int
    name: str
    url: str
    port: int
    available_for_all: bool  # Can be used by all selected miners
    avalon_only: bool  # Only in Avalon Nano slots


class AvailablePoolsResponse(BaseModel):
    """Response with available pools based on miner selection"""
    has_avalon_nano: bool
    has_bitaxe_or_nerdqaxe: bool
    has_mixed_types: bool
    warning_message: Optional[str]
    pools: List[PoolOption]


@router.get("/strategy-pools/available", response_model=AvailablePoolsResponse)
async def get_available_pools_for_strategy(
    miner_ids: str = Query(default="", description="Comma-separated miner IDs, empty for all"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get available pools based on selected miners for strategy creation.
    
    Logic:
    - If only Avalon Nano: Return only pools in their 3 slots (intersection)
    - If only Bitaxe/NerdQaxe: Return all enabled pools
    - If mixed: Return all pools, but mark which are available for all vs only some
    - If no miners selected: Return all enabled pools (strategy applies to all)
    """
    
    # Parse miner IDs
    if miner_ids:
        miner_id_list = [int(mid.strip()) for mid in miner_ids.split(",") if mid.strip()]
    else:
        miner_id_list = []
    
    # If no miners specified, strategy applies to all miners
    if not miner_id_list:
        # Get all enabled pools
        result = await db.execute(
            select(Pool).where(Pool.enabled == True).order_by(Pool.name)
        )
        all_pools = result.scalars().all()
        
        # Check what device types exist in the system
        nano_result = await db.execute(
            select(Miner).where(
                and_(
                    Miner.miner_type == "avalon_nano",
                    Miner.enabled == True
                )
            )
        )
        avalon_miners = list(nano_result.scalars().all())
        has_avalons = len(avalon_miners) > 0
        
        other_result = await db.execute(
            select(Miner).where(
                and_(
                    Miner.miner_type != "avalon_nano",
                    Miner.enabled == True
                )
            )
        )
        has_others = len(list(other_result.scalars().all())) > 0
        
        # If we have mixed device types, show which pools work with all vs only some
        if has_avalons and has_others:
            # Get Avalon pool slots to determine which pools work with all devices
            avalon_miner_ids = [m.id for m in avalon_miners]
            result = await db.execute(
                select(MinerPoolSlot).where(
                    MinerPoolSlot.miner_id.in_(avalon_miner_ids)
                )
            )
            slots = list(result.scalars().all())
            
            avalon_pool_ids = set()
            if slots:
                for slot in slots:
                    if slot.pool_id:
                        avalon_pool_ids.add(slot.pool_id)
            
            if not avalon_pool_ids:
                warning = "Strategy will apply to all miners. ⚠️ Avalon pool slots not yet synced - all pools shown but Avalon miners may only switch to pools in their configured slots."
            else:
                warning = "Strategy will apply to all miners. Pools marked 'All Devices' work for both types; others work only for Bitaxe/NerdQaxe."
            
            pools = [
                PoolOption(
                    id=p.id,
                    name=p.name,
                    url=p.url,
                    port=p.port,
                    available_for_all=(p.id in avalon_pool_ids) if avalon_pool_ids else True,
                    avalon_only=False
                )
                for p in all_pools
            ]
            
            return AvailablePoolsResponse(
                has_avalon_nano=True,
                has_bitaxe_or_nerdqaxe=True,
                has_mixed_types=True,  # Show badges since we have mixed device types
                warning_message=warning,
                pools=pools
            )
        else:
            # Only one device type or no devices - no badges needed
            warning = None
            if has_avalons:
                warning = "Strategy will apply to all miners. Note: Avalon Nano miners can only use pools configured in their 3 slots."
            
            pools = [
                PoolOption(
                    id=p.id,
                    name=p.name,
                    url=p.url,
                    port=p.port,
                    available_for_all=True,
                    avalon_only=False
                )
                for p in all_pools
            ]
            
            return AvailablePoolsResponse(
                has_avalon_nano=has_avalons,
                has_bitaxe_or_nerdqaxe=has_others,
                has_mixed_types=False,  # Only one type, no badges needed
                warning_message=warning,
                pools=pools
            )
    
    # Get selected miners
    result = await db.execute(
        select(Miner).where(
            and_(
                Miner.id.in_(miner_id_list),
                Miner.enabled == True
            )
        )
    )
    selected_miners = list(result.scalars().all())
    
    if not selected_miners:
        return AvailablePoolsResponse(
            has_avalon_nano=False,
            has_bitaxe_or_nerdqaxe=False,
            has_mixed_types=False,
            warning_message="No enabled miners selected",
            pools=[]
        )
    
    # Categorize miners
    avalon_miners = [m for m in selected_miners if m.miner_type == "avalon_nano"]
    other_miners = [m for m in selected_miners if m.miner_type != "avalon_nano"]
    
    has_avalon = len(avalon_miners) > 0
    has_others = len(other_miners) > 0
    is_mixed = has_avalon and has_others
    
    warning = None
    available_pools = []
    
    if has_avalon and not has_others:
        # ONLY Avalon Nano miners - show all pools (dynamic switching supported)
        result = await db.execute(
            select(Pool).where(Pool.enabled == True).order_by(Pool.name)
        )
        all_pools = list(result.scalars().all())
        
        pools = [
            PoolOption(
                id=p.id,
                name=p.name,
                url=p.url,
                port=p.port,
                available_for_all=True,
                avalon_only=False
            )
            for p in all_pools
        ]
        
    elif has_others and not has_avalon:
        # ONLY Bitaxe/NerdQaxe - return all enabled pools
        result = await db.execute(
            select(Pool).where(Pool.enabled == True).order_by(Pool.name)
        )
        all_pools = result.scalars().all()
        
        pools = [
            PoolOption(
                id=p.id,
                name=p.name,
                url=p.url,
                port=p.port,
                available_for_all=True,
                avalon_only=False
            )
            for p in all_pools
        ]
        
    else:
        # MIXED device types - All miners now support dynamic pool switching
        result = await db.execute(
            select(Pool).where(Pool.enabled == True).order_by(Pool.name)
        )
        all_pools = list(result.scalars().all())
        
        pools = [
            PoolOption(
                id=p.id,
                name=p.name,
                url=p.url,
                port=p.port,
                available_for_all=True,
                avalon_only=False
            )
            for p in all_pools
        ]
    
    return AvailablePoolsResponse(
        has_avalon_nano=has_avalon,
        has_bitaxe_or_nerdqaxe=has_others,
        has_mixed_types=is_mixed,
        warning_message=warning,
        pools=pools
    )
