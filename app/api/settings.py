"""
Settings API endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from core.database import get_db, Miner, Pool, Telemetry
from core.config import app_config
from core.solopool import SolopoolService

router = APIRouter()


class SolopoolSettings(BaseModel):
    enabled: bool


@router.get("/solopool")
async def get_solopool_settings():
    """Get Solopool.org integration settings"""
    return {
        "enabled": app_config.get("solopool_enabled", False)
    }


@router.post("/solopool")
async def save_solopool_settings(settings: SolopoolSettings):
    """Save Solopool.org integration settings"""
    app_config.set("solopool_enabled", settings.enabled)
    app_config.save()
    
    return {
        "message": "Solopool settings saved",
        "enabled": settings.enabled
    }


@router.get("/solopool/stats")
async def get_solopool_stats(db: AsyncSession = Depends(get_db)):
    """Get Solopool stats for all miners using Solopool pools (BCH, DGB, and BTC)"""
    # Check if Solopool integration is enabled
    if not app_config.get("solopool_enabled", False):
        return {"enabled": False, "bch_miners": [], "dgb_miners": [], "btc_miners": []}
    
    # Get all pools
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    bch_pools = {}
    dgb_pools = {}
    btc_pools = {}
    for pool in all_pools:
        if SolopoolService.is_solopool_bch_pool(pool.url, pool.port):
            bch_pools[pool.url] = pool
        elif SolopoolService.is_solopool_dgb_pool(pool.url, pool.port):
            dgb_pools[pool.url] = pool
        elif SolopoolService.is_solopool_btc_pool(pool.url, pool.port):
            btc_pools[pool.url] = pool
    
    if not bch_pools and not dgb_pools and not btc_pools:
        return {"enabled": True, "bch_miners": [], "dgb_miners": [], "btc_miners": []}
    
    # Get all enabled miners
    miner_result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = miner_result.scalars().all()
    
    bch_stats_list = []
    dgb_stats_list = []
    btc_stats_list = []
    bch_processed_usernames = set()
    dgb_processed_usernames = set()
    btc_processed_usernames = set()
    
    for miner in miners:
        # Get latest telemetry to see which pool they're using
        telemetry_result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner.id)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        latest_telemetry = telemetry_result.scalar_one_or_none()
        
        if not latest_telemetry or not latest_telemetry.pool_in_use:
            continue
        
        pool_in_use = latest_telemetry.pool_in_use
        
        # Check BCH pools
        matching_pool = None
        for pool_url, pool_obj in bch_pools.items():
            if pool_url in pool_in_use:
                matching_pool = pool_obj
                break
        
        if matching_pool:
            username = SolopoolService.extract_username(matching_pool.user)
            if username not in bch_processed_usernames:
                bch_processed_usernames.add(username)
                bch_stats = await SolopoolService.get_bch_account_stats(username)
                if bch_stats:
                    bch_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "BCH",
                        "stats": SolopoolService.format_stats_summary(bch_stats)
                    })
            continue
        
        # Check DGB pools
        matching_pool = None
        for pool_url, pool_obj in dgb_pools.items():
            if pool_url in pool_in_use:
                matching_pool = pool_obj
                break
        
        if matching_pool:
            username = SolopoolService.extract_username(matching_pool.user)
            if username not in dgb_processed_usernames:
                dgb_processed_usernames.add(username)
                dgb_stats = await SolopoolService.get_dgb_account_stats(username)
                if dgb_stats:
                    dgb_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "DGB",
                        "stats": SolopoolService.format_stats_summary(dgb_stats)
                    })
            continue
        
        # Check BTC pools
        matching_pool = None
        for pool_url, pool_obj in btc_pools.items():
            if pool_url in pool_in_use:
                matching_pool = pool_obj
                break
        
        if matching_pool:
            username = SolopoolService.extract_username(matching_pool.user)
            if username not in btc_processed_usernames:
                btc_processed_usernames.add(username)
                btc_stats = await SolopoolService.get_btc_account_stats(username)
                if btc_stats:
                    btc_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "BTC",
                        "stats": SolopoolService.format_stats_summary(btc_stats)
                    })
    
    return {
        "enabled": True,
        "bch_miners": bch_stats_list,
        "dgb_miners": dgb_stats_list,
        "btc_miners": btc_stats_list
    }
