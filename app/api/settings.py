"""
Settings API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx
import logging
import os
import signal

from core.database import get_db, Miner, Pool, Telemetry, Event, AsyncSessionLocal, CryptoPrice
from core.config import app_config
from core.solopool import SolopoolService
from core.braiins import BraiinsPoolService, get_braiins_summary
from core.nerdminers import NerdMinersService
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/restart")
async def restart_application():
    """Restart the application container"""
    logger.info("Application restart requested via API")
    
    # Log the restart event
    async with AsyncSessionLocal() as db:
        event = Event(
            event_type="info",
            source="api",
            message="Application restart initiated from settings"
        )
        db.add(event)
        await db.commit()
    
    # Send SIGTERM to trigger graceful shutdown, Docker will restart us
    os.kill(os.getpid(), signal.SIGTERM)
    
    return {"message": "Restarting application..."}


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


class BraiinsSettings(BaseModel):
    enabled: bool
    api_token: Optional[str] = None


class CloudPushSettings(BaseModel):
    enabled: bool
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    push_interval: Optional[int] = 300


@router.get("/cloud")
async def get_cloud_settings():
    """Get cloud push settings"""
    return {
        "enabled": app_config.get("cloud.enabled", False),
        "endpoint": app_config.get("cloud.endpoint", "https://stage.miningpool.uk"),
        "api_key": app_config.get("cloud.api_key", ""),
        "push_interval": app_config.get("cloud.push_interval", 300)
    }


@router.post("/cloud")
async def save_cloud_settings(settings: CloudPushSettings):
    """Save cloud push settings"""
    if settings.enabled and (not settings.endpoint or not settings.api_key):
        return {
            "message": "Endpoint and API key are required when cloud push is enabled",
            "enabled": False
        }
    
    app_config.set("cloud.enabled", settings.enabled)
    if settings.endpoint:
        app_config.set("cloud.endpoint", settings.endpoint)
    if settings.api_key:
        app_config.set("cloud.api_key", settings.api_key)
    if settings.push_interval:
        app_config.set("cloud.push_interval", settings.push_interval)
    
    return {
        "message": "Cloud push settings saved",
        "enabled": settings.enabled
    }


@router.get("/braiins")
async def get_braiins_settings():
    """Get Braiins Pool integration settings"""
    return {
        "enabled": app_config.get("braiins_enabled", False),
        "api_token": app_config.get("braiins_api_token", "")
    }


@router.post("/braiins")
async def save_braiins_settings(settings: BraiinsSettings):
    """Save Braiins Pool integration settings"""
    if settings.enabled and not settings.api_token:
        return {
            "message": "API token is required when integration is enabled",
            "enabled": False
        }
    
    app_config.set("braiins_enabled", settings.enabled)
    app_config.set("braiins_api_token", settings.api_token or "")
    app_config.save()
    
    return {
        "message": "Braiins Pool settings saved",
        "enabled": settings.enabled
    }


@router.get("/braiins/stats")
async def get_braiins_stats(db: AsyncSession = Depends(get_db)):
    """Get Braiins Pool stats for miners using Braiins Pool"""
    from core.database import AgileStrategy
    from core.agile_bands import get_strategy_bands
    
    # Check if Braiins integration is enabled
    if not app_config.get("braiins_enabled", False):
        return {"enabled": False, "stats": None, "show_always": False}
    
    api_token = app_config.get("braiins_api_token", "")
    if not api_token:
        return {"enabled": False, "stats": None, "error": "No API token configured", "show_always": False}
    
    # Check if BTC_POOLED is configured in Agile Strategy bands
    show_always = False
    strategy_result = await db.execute(select(AgileStrategy))
    strategy = strategy_result.scalar_one_or_none()
    
    if strategy and strategy.enabled:
        bands = await get_strategy_bands(db, strategy.id)
        # Check if any band uses BTC_POOLED
        show_always = any(band.target_coin == "BTC_POOLED" for band in bands)
    
    # Check if any miners are using Braiins Pool
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    braiins_pools = [p for p in all_pools if BraiinsPoolService.is_braiins_pool(p.url, p.port)]
    
    if not braiins_pools:
        # Return empty stats structure so tiles show (greyed out) if show_always
        empty_stats = {
            "workers_online": 0,
            "workers_offline": 0,
            "hashrate_5m": None,
            "current_balance": 0,
            "today_reward": 0,
            "all_time_reward": 0
        }
        return {"enabled": True, "stats": empty_stats, "username": "", "workers_using": 0, "show_always": show_always}
    
    # Get miners using Braiins pools
    miner_result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = miner_result.scalars().all()
    
    miners_using_braiins = 0
    for miner in miners:
        telemetry_result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner.id)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        latest_telemetry = telemetry_result.scalar_one_or_none()
        
        if latest_telemetry and latest_telemetry.pool_in_use:
            if "braiins.com" in latest_telemetry.pool_in_use.lower():
                miners_using_braiins += 1
    
    # Get username from the first Braiins pool (they should all have same username)
    braiins_username = ""
    if braiins_pools:
        # Extract username from pool user (format: username.workername or just username)
        pool_user = braiins_pools[0].user
        braiins_username = pool_user.split('.')[0] if pool_user else ""
    
    stats = await get_braiins_summary()
    if not stats:
        stats = {
            "workers_online": 0,
            "workers_offline": 0,
            "hashrate_5m": None,
            "current_balance": 0,
            "today_reward": 0,
            "all_time_reward": 0
        }
    
    return {
        "enabled": True,
        "stats": stats,
        "username": braiins_username,
        "workers_using": miners_using_braiins,
        "show_always": show_always
    }


@router.get("/nerdminers/stats")
async def get_nerdminers_stats(db: AsyncSession = Depends(get_db)):
    """Get NerdMiners Pool stats for miners using NerdMiners Pool"""
    # Get all pools
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    nerdminers_pools = {}
    for pool in all_pools:
        if NerdMinersService.is_nerdminers_pool(pool.url, pool.port):
            nerdminers_pools[pool.user] = pool
    
    if not nerdminers_pools:
        return {"enabled": False, "btc_miners": []}
    
    # Get pool status for network stats
    pool_status = await NerdMinersService.get_pool_status()
    
    # Get all enabled miners
    miner_result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = miner_result.scalars().all()
    
    btc_stats_list = []
    processed_wallets = set()
    
    for miner in miners:
        # Get latest telemetry
        telemetry_result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner.id)
            .order_by(Telemetry.timestamp.desc())
            .limit(1)
        )
        latest_telemetry = telemetry_result.scalar_one_or_none()
        
        # Check if mining to NerdMiners pool
        if latest_telemetry and latest_telemetry.pool_in_use:
            if "pool.nerdminers.org" in latest_telemetry.pool_in_use.lower():
                # Get wallet from pool config
                matching_pool = next(
                    (p for p in nerdminers_pools.values()
                     if f"{p.url}:{p.port}" in latest_telemetry.pool_in_use),
                    None
                )
                
                if matching_pool and matching_pool.user not in processed_wallets:
                    processed_wallets.add(matching_pool.user)
                    
                    # Fetch user stats
                    user_stats = await NerdMinersService.get_user_stats(matching_pool.user)
                    formatted_stats = NerdMinersService.format_stats_summary(user_stats, pool_status)
                    
                    btc_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": matching_pool.user,
                        "coin": "BTC",
                        "stats": formatted_stats,
                        "is_strategy_pool": False,
                        "is_active_target": False
                    })
    
    return {
        "enabled": True,
        "btc_miners": btc_stats_list
    }


@router.get("/solopool/stats")
async def get_solopool_stats(db: AsyncSession = Depends(get_db)):
    """Get Solopool stats for all miners using Solopool pools (BCH, DGB, BTC)"""
    # Check if Solopool integration is enabled
    if not app_config.get("solopool_enabled", False):
        return {"enabled": False, "strategy_enabled": False, "active_target": None, "bch_miners": [], "dgb_miners": [], "btc_miners": []}
    
    # Check if Agile Solo Strategy is enabled
    from core.database import AgileStrategy
    from core.agile_bands import ensure_strategy_bands, get_strategy_bands, get_band_for_price
    from core.agile_solo_strategy import AgileSoloStrategy
    
    strategy_result = await db.execute(select(AgileStrategy))
    strategy = strategy_result.scalar_one_or_none()
    strategy_enabled = strategy and strategy.enabled
    current_band = strategy.current_price_band if strategy else None
    
    # Dashboard simply shows what strategy last decided - no duplicate logic
    active_target = None
    if strategy_enabled and strategy:
        # Just show what strategy execution set in database
        if strategy.current_price_band and strategy.current_price_band != "OFF":
            active_target = strategy.current_price_band
    
    # Get all pools
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    bch_pools = {}
    dgb_pools = {}
    btc_pools = {}
    bc2_pools = {}
    for pool in all_pools:
        if SolopoolService.is_solopool_bch_pool(pool.url, pool.port):
            bch_pools[pool.url] = pool
        elif SolopoolService.is_solopool_dgb_pool(pool.url, pool.port):
            dgb_pools[pool.url] = pool
        elif SolopoolService.is_solopool_btc_pool(pool.url, pool.port):
            btc_pools[pool.url] = pool
        elif SolopoolService.is_solopool_bc2_pool(pool.url, pool.port):
            bc2_pools[pool.url] = pool
    
    if not bch_pools and not dgb_pools and not btc_pools and not bc2_pools:
        return {"enabled": True, "bch_miners": [], "dgb_miners": [], "btc_miners": [], "bc2_miners": []}
    
    # Fetch network/pool stats for ETTB calculation
    bch_network_stats = await SolopoolService.get_bch_pool_stats() if bch_pools else None
    dgb_network_stats = await SolopoolService.get_dgb_pool_stats() if dgb_pools else None
    btc_network_stats = await SolopoolService.get_btc_pool_stats() if btc_pools else None
    bc2_network_stats = await SolopoolService.get_bc2_pool_stats() if bc2_pools else None
    
    # Get all enabled miners
    miner_result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = miner_result.scalars().all()
    
    bch_stats_list = []
    dgb_stats_list = []
    btc_stats_list = []
    bc2_stats_list = []
    bch_processed_usernames = set()
    dgb_processed_usernames = set()
    btc_processed_usernames = set()
    bc2_processed_usernames = set()
    
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
                    formatted_stats = SolopoolService.format_stats_summary(bch_stats)
                    # Calculate ETTB (BCH block time: 600 seconds)
                    if bch_network_stats:
                        network_hashrate = bch_network_stats.get("stats", {}).get("hashrate", 0)
                        user_hashrate = formatted_stats.get("hashrate_raw", 0)
                        ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 600)
                        formatted_stats["ettb"] = ettb
                        formatted_stats["network_hashrate"] = network_hashrate
                    
                    bch_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "BCH",
                        "stats": formatted_stats
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
                    formatted_stats = SolopoolService.format_stats_summary(dgb_stats)
                    # Calculate ETTB (DGB block time: 15 seconds)
                    if dgb_network_stats:
                        network_hashrate = dgb_network_stats.get("stats", {}).get("hashrate", 0)
                        user_hashrate = formatted_stats.get("hashrate_raw", 0)
                        ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 15)
                        formatted_stats["ettb"] = ettb
                        formatted_stats["network_hashrate"] = network_hashrate
                    
                    dgb_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "DGB",
                        "stats": formatted_stats
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
                    formatted_stats = SolopoolService.format_stats_summary(btc_stats)
                    # Calculate ETTB (BTC block time: 600 seconds)
                    if btc_network_stats:
                        network_hashrate = btc_network_stats.get("stats", {}).get("hashrate", 0)
                        user_hashrate = formatted_stats.get("hashrate_raw", 0)
                        ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 600)
                        formatted_stats["ettb"] = ettb
                        formatted_stats["network_hashrate"] = network_hashrate
                    
                    btc_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "BTC",
                        "stats": formatted_stats
                    })
            continue
        
        # Check BC2 pools
        matching_pool = None
        for pool_url, pool_obj in bc2_pools.items():
            if pool_url in pool_in_use:
                matching_pool = pool_obj
                break
        
        if matching_pool:
            username = SolopoolService.extract_username(matching_pool.user)
            if username not in bc2_processed_usernames:
                bc2_processed_usernames.add(username)
                bc2_stats = await SolopoolService.get_bc2_account_stats(username)
                if bc2_stats:
                    formatted_stats = SolopoolService.format_stats_summary(bc2_stats)
                    # Calculate ETTB (BC2 block time: 600 seconds - assuming same as BTC)
                    if bc2_network_stats:
                        network_hashrate = bc2_network_stats.get("stats", {}).get("hashrate", 0)
                        user_hashrate = formatted_stats.get("hashrate_raw", 0)
                        ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 600)
                        formatted_stats["ettb"] = ettb
                        formatted_stats["network_hashrate"] = network_hashrate
                    
                    bc2_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "BC2",
                        "stats": formatted_stats
                    })
            continue
    
    # If Agile Solo Strategy is enabled, ensure DGB/BTC/BCH tiles always exist (even with 0 miners)
    if strategy_enabled:
        # Create stub for DGB if no active miners
        if not dgb_stats_list and dgb_pools:
            # Get first DGB pool for username
            first_dgb_pool = next(iter(dgb_pools.values()))
            username = SolopoolService.extract_username(first_dgb_pool.user)
            dgb_stats = await SolopoolService.get_dgb_account_stats(username)
            if dgb_stats:
                formatted_stats = SolopoolService.format_stats_summary(dgb_stats)
                # Calculate ETTB
                if dgb_network_stats:
                    network_hashrate = dgb_network_stats.get("stats", {}).get("hashrate", 0)
                    user_hashrate = formatted_stats.get("hashrate_raw", 0)
                    ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 15)
                    formatted_stats["ettb"] = ettb
                    formatted_stats["network_hashrate"] = network_hashrate
                
                dgb_stats_list.append({
                    "miner_id": None,
                    "miner_name": "No miners assigned",
                    "pool_url": first_dgb_pool.url,
                    "pool_port": first_dgb_pool.port,
                    "username": username,
                    "coin": "DGB",
                    "stats": formatted_stats,
                    "is_strategy_pool": True,
                    "is_active_target": active_target == "DGB"
                })
        
        # Create stub for BTC if no active miners
        if not btc_stats_list and btc_pools:
            first_btc_pool = next(iter(btc_pools.values()))
            username = SolopoolService.extract_username(first_btc_pool.user)
            btc_stats = await SolopoolService.get_btc_account_stats(username)
            if btc_stats:
                formatted_stats = SolopoolService.format_stats_summary(btc_stats)
                if btc_network_stats:
                    network_hashrate = btc_network_stats.get("stats", {}).get("hashrate", 0)
                    user_hashrate = formatted_stats.get("hashrate_raw", 0)
                    ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 600)
                    formatted_stats["ettb"] = ettb
                    formatted_stats["network_hashrate"] = network_hashrate
                
                btc_stats_list.append({
                    "miner_id": None,
                    "miner_name": "No miners assigned",
                    "pool_url": first_btc_pool.url,
                    "pool_port": first_btc_pool.port,
                    "username": username,
                    "coin": "BTC",
                    "stats": formatted_stats,
                    "is_strategy_pool": True,
                    "is_active_target": active_target == "BTC"
                })
        
        # Create stub for BCH if no active miners
        if not bch_stats_list and bch_pools:
            first_bch_pool = next(iter(bch_pools.values()))
            username = SolopoolService.extract_username(first_bch_pool.user)
            bch_stats = await SolopoolService.get_bch_account_stats(username)
            if bch_stats:
                formatted_stats = SolopoolService.format_stats_summary(bch_stats)
                if bch_network_stats:
                    network_hashrate = bch_network_stats.get("stats", {}).get("hashrate", 0)
                    user_hashrate = formatted_stats.get("hashrate_raw", 0)
                    ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 600)
                    formatted_stats["ettb"] = ettb
                    formatted_stats["network_hashrate"] = network_hashrate
                
                bch_stats_list.append({
                    "miner_id": None,
                    "miner_name": "No miners assigned",
                    "pool_url": first_bch_pool.url,
                    "pool_port": first_bch_pool.port,
                    "username": username,
                    "coin": "BCH",
                    "stats": formatted_stats,
                    "is_strategy_pool": True,
                    "is_active_target": active_target == "BCH"
                })
        
        # Create stub for BC2 if no active miners
        if not bc2_stats_list and bc2_pools:
            first_bc2_pool = next(iter(bc2_pools.values()))
            username = SolopoolService.extract_username(first_bc2_pool.user)
            bc2_stats = await SolopoolService.get_bc2_account_stats(username)
            if bc2_stats:
                formatted_stats = SolopoolService.format_stats_summary(bc2_stats)
                if bc2_network_stats:
                    network_hashrate = bc2_network_stats.get("stats", {}).get("hashrate", 0)
                    user_hashrate = formatted_stats.get("hashrate_raw", 0)
                    ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 600)
                    formatted_stats["ettb"] = ettb
                    formatted_stats["network_hashrate"] = network_hashrate
                
                bc2_stats_list.append({
                    "miner_id": None,
                    "miner_name": "No miners assigned",
                    "pool_url": first_bc2_pool.url,
                    "pool_port": first_bc2_pool.port,
                    "username": username,
                    "coin": "BC2",
                    "stats": formatted_stats,
                    "is_strategy_pool": True,
                    "is_active_target": active_target == "BC2"
                })
        
        # Mark existing entries as strategy pools and set active status
        for entry in dgb_stats_list:
            if "is_strategy_pool" not in entry:
                entry["is_strategy_pool"] = True
                entry["is_active_target"] = active_target == "DGB"
        for entry in btc_stats_list:
            if "is_strategy_pool" not in entry:
                entry["is_strategy_pool"] = True
                entry["is_active_target"] = active_target == "BTC"
        for entry in bch_stats_list:
            if "is_strategy_pool" not in entry:
                entry["is_strategy_pool"] = True
                entry["is_active_target"] = active_target == "BCH"
        for entry in bc2_stats_list:
            if "is_strategy_pool" not in entry:
                entry["is_strategy_pool"] = True
                entry["is_active_target"] = active_target == "BC2"
    
    # Sort: strategy pools first (DGB → BC2 → BCH → BTC order)
    def sort_key(entry):
        if entry.get("is_strategy_pool"):
            coin = entry.get("coin", "")
            if coin == "DGB":
                return (0, 0)  # First (LOW)
            elif coin == "BC2":
                return (0, 1)  # Second
            elif coin == "BCH":
                return (0, 2)  # Third (MED)
            elif coin == "BTC":
                return (0, 3)  # Fourth (HIGH)
        return (1, entry.get("coin", ""))  # Other pools after
    
    dgb_stats_list.sort(key=sort_key)
    btc_stats_list.sort(key=sort_key)
    bch_stats_list.sort(key=sort_key)
    bc2_stats_list.sort(key=sort_key)
    
    return {
        "enabled": True,
        "strategy_enabled": strategy_enabled,
        "active_target": active_target,
        "bch_miners": bch_stats_list,
        "dgb_miners": dgb_stats_list,
        "btc_miners": btc_stats_list,
        "bc2_miners": bc2_stats_list
    }


@router.get("/solopool/charts")
async def get_solopool_charts(db: AsyncSession = Depends(get_db)):
    """Get Solopool chart data for sparkline visualization for all coins (24-hour rolling window)"""
    from datetime import datetime, timedelta
    
    # Check if Solopool integration is enabled
    if not app_config.get("solopool_enabled", False):
        return {"enabled": False, "charts": {}}
    
    # Get all pools
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    dgb_pools = {}
    bch_pools = {}
    btc_pools = {}
    bc2_pools = {}
    xmr_pools = {}
    
    for pool in all_pools:
        if SolopoolService.is_solopool_dgb_pool(pool.url, pool.port):
            dgb_pools[pool.url] = pool
        elif SolopoolService.is_solopool_bch_pool(pool.url, pool.port):
            bch_pools[pool.url] = pool
        elif SolopoolService.is_solopool_btc_pool(pool.url, pool.port):
            btc_pools[pool.url] = pool
        elif SolopoolService.is_solopool_bc2_pool(pool.url, pool.port):
            bc2_pools[pool.url] = pool
        elif SolopoolService.is_solopool_xmr_pool(pool.url, pool.port):
            xmr_pools[pool.url] = pool
    
    # Calculate 24-hour cutoff timestamp
    cutoff_timestamp = int((datetime.utcnow() - timedelta(hours=24)).timestamp())
    
    charts_data = {}
    
    # Fetch DGB charts (24-hour rolling window)
    if dgb_pools:
        first_dgb_pool = next(iter(dgb_pools.values()))
        username = SolopoolService.extract_username(first_dgb_pool.user)
        if username:
            dgb_stats = await SolopoolService.get_dgb_account_stats(username, use_cache=False)
            if dgb_stats and "charts" in dgb_stats:
                charts = dgb_stats.get("charts", [])
                # Filter to only last 24 hours based on timestamp
                charts_data["dgb"] = [c for c in charts if c.get("x", 0) >= cutoff_timestamp]
    
    # Fetch BCH charts (24-hour rolling window)
    if bch_pools:
        first_bch_pool = next(iter(bch_pools.values()))
        username = SolopoolService.extract_username(first_bch_pool.user)
        if username:
            bch_stats = await SolopoolService.get_bch_account_stats(username, use_cache=False)
            if bch_stats and "charts" in bch_stats:
                charts = bch_stats.get("charts", [])
                # Filter to only last 24 hours based on timestamp
                charts_data["bch"] = [c for c in charts if c.get("x", 0) >= cutoff_timestamp]
    
    # Fetch BTC charts (24-hour rolling window)
    if btc_pools:
        first_btc_pool = next(iter(btc_pools.values()))
        username = SolopoolService.extract_username(first_btc_pool.user)
        if username:
            btc_stats = await SolopoolService.get_btc_account_stats(username, use_cache=False)
            if btc_stats and "charts" in btc_stats:
                charts = btc_stats.get("charts", [])
                # Filter to only last 24 hours based on timestamp
                charts_data["btc"] = [c for c in charts if c.get("x", 0) >= cutoff_timestamp]
    
    # Fetch BC2 charts (24-hour rolling window)
    if bc2_pools:
        first_bc2_pool = next(iter(bc2_pools.values()))
        username = SolopoolService.extract_username(first_bc2_pool.user)
        if username:
            bc2_stats = await SolopoolService.get_bc2_account_stats(username, use_cache=False)
            if bc2_stats and "charts" in bc2_stats:
                charts = bc2_stats.get("charts", [])
                # Filter to only last 24 hours based on timestamp
                charts_data["bc2"] = [c for c in charts if c.get("x", 0) >= cutoff_timestamp]
    
    # Fetch XMR charts (24-hour rolling window)
    if xmr_pools:
        first_xmr_pool = next(iter(xmr_pools.values()))
        username = SolopoolService.extract_username(first_xmr_pool.user)
        if username:
            xmr_stats = await SolopoolService.get_xmr_account_stats(username, use_cache=False)
            if xmr_stats and "charts" in xmr_stats:
                charts = xmr_stats.get("charts", [])
                # Filter to only last 24 hours based on timestamp
                charts_data["xmr"] = [c for c in charts if c.get("x", 0) >= cutoff_timestamp]
    
    return {"enabled": True, "charts": charts_data}


@router.get("/crypto-prices")
async def get_crypto_prices():
    """Return cached crypto prices (updated every 10 minutes by scheduler)"""
    prices = {
        "bitcoin-cash": 0,
        "bellscoin": 0,
        "digibyte": 0,
        "bitcoin": 0,
        "success": False,
        "error": None,
        "source": None,
        "cache_age": None
    }
    
    # Get cached prices from database
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CryptoPrice))
        cached_prices = {cp.coin_id: cp for cp in result.scalars().all()}
        
        if cached_prices:
            prices["bitcoin"] = cached_prices.get("bitcoin").price_gbp if "bitcoin" in cached_prices else 0
            prices["bitcoin-cash"] = cached_prices.get("bitcoin-cash").price_gbp if "bitcoin-cash" in cached_prices else 0
            prices["bellscoin"] = cached_prices.get("bellscoin").price_gbp if "bellscoin" in cached_prices else 0
            prices["digibyte"] = cached_prices.get("digibyte").price_gbp if "digibyte" in cached_prices else 0
            prices["success"] = True
            prices["source"] = cached_prices.get("bitcoin").source if "bitcoin" in cached_prices else "cache"
            
            # Calculate cache age
            if "bitcoin" in cached_prices:
                age = datetime.utcnow() - cached_prices["bitcoin"].updated_at
                age_minutes = int(age.total_seconds() / 60)
                prices["cache_age"] = f"{age_minutes}m ago"
                prices["age_minutes"] = age_minutes
            
            return prices
        else:
            prices["error"] = "No cached prices available yet"
            return prices


async def fetch_and_cache_crypto_prices():
    """Fetch crypto prices in GBP with fallback across multiple free APIs and cache them"""
    prices = {
        "bitcoin-cash": 0,
        "bellscoin": 0,
        "digibyte": 0,
        "bitcoin": 0,
        "success": False,
        "error": None,
        "source": None
    }
    
    # Try CoinGecko first
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={
                    'ids': 'bitcoin-cash,bellscoin,digibyte,bitcoin',
                    'vs_currencies': 'gbp'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                prices["bitcoin-cash"] = data.get("bitcoin-cash", {}).get("gbp", 0)
                prices["bellscoin"] = data.get("bellscoin", {}).get("gbp", 0)
                prices["digibyte"] = data.get("digibyte", {}).get("gbp", 0)
                prices["bitcoin"] = data.get("bitcoin", {}).get("gbp", 0)
                prices["success"] = True
                prices["source"] = "coingecko"
                
                logger.info(f"Fetched crypto prices from CoinGecko: BCH=£{prices['bitcoin-cash']}, BC2=£{prices['bellscoin']}, DGB=£{prices['digibyte']}, BTC=£{prices['bitcoin']}")
                return prices
            else:
                error_msg = f"CoinGecko API returned status {response.status_code}: {response.text[:200]}"
                logger.warning(error_msg)
                
                async with AsyncSessionLocal() as session:
                    event = Event(
                        event_type="api_warning",
                        source="coingecko",
                        message=error_msg
                    )
                    session.add(event)
                    await session.commit()
                    
    except Exception as e:
        logger.warning(f"CoinGecko API failed: {str(e)}")
    
    # Fallback to CoinCap API
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # CoinCap uses different IDs: bitcoin-cash, bellscoin, digibyte, bitcoin
            bch_response = await client.get('https://api.coincap.io/v2/assets/bitcoin-cash')
            bc2_response = await client.get('https://api.coincap.io/v2/assets/bellscoin')
            dgb_response = await client.get('https://api.coincap.io/v2/assets/digibyte')
            btc_response = await client.get('https://api.coincap.io/v2/assets/bitcoin')
            
            # Get GBP exchange rate
            gbp_response = await client.get('https://api.coincap.io/v2/rates/british-pound-sterling')
            
            if all(r.status_code == 200 for r in [bch_response, bc2_response, dgb_response, btc_response, gbp_response]):
                gbp_rate = float(gbp_response.json()["data"]["rateUsd"])
                
                bch_usd = float(bch_response.json()["data"]["priceUsd"])
                bc2_usd = float(bc2_response.json()["data"]["priceUsd"])
                dgb_usd = float(dgb_response.json()["data"]["priceUsd"])
                btc_usd = float(btc_response.json()["data"]["priceUsd"])
                
                prices["bitcoin-cash"] = bch_usd / gbp_rate
                prices["bellscoin"] = bc2_usd / gbp_rate
                prices["digibyte"] = dgb_usd / gbp_rate
                prices["bitcoin"] = btc_usd / gbp_rate
                prices["success"] = True
                prices["source"] = "coincap"
                
                logger.info(f"Fetched crypto prices from CoinCap: BCH=£{prices['bitcoin-cash']:.2f}, BC2=£{prices['bellscoin']:.6f}, DGB=£{prices['digibyte']:.6f}, BTC=£{prices['bitcoin']:.2f}")
                return prices
            else:
                logger.warning("CoinCap API returned non-200 status")
                
    except Exception as e:
        logger.warning(f"CoinCap API failed: {str(e)}")
    
    # Fallback to Binance API (convert via USDT then to GBP)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Binance provides direct GBP pairs for BTC, BCH
            btc_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCGBP')
            bch_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=BCHGBP')
            
            # DGB and BC2 not on Binance with GBP, get USDT price and convert
            dgb_usdt_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=DGBUSDT')
            # BC2 likely not on Binance, try but don't fail if not available
            try:
                bc2_usdt_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=BLS2USDT')
            except:
                bc2_usdt_response = None
            usdt_gbp_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=GBPUSDT')
            
            if all(r.status_code == 200 for r in [btc_response, bch_response, dgb_usdt_response, usdt_gbp_response]):
                prices["bitcoin"] = float(btc_response.json()["price"])
                prices["bitcoin-cash"] = float(bch_response.json()["price"])
                
                dgb_usdt = float(dgb_usdt_response.json()["price"])
                gbp_usdt = float(usdt_gbp_response.json()["price"])
                prices["digibyte"] = dgb_usdt / gbp_usdt
                
                # Try to get BC2 price if available
                if bc2_usdt_response and bc2_usdt_response.status_code == 200:
                    bc2_usdt = float(bc2_usdt_response.json()["price"])
                    prices["bellscoin"] = bc2_usdt / gbp_usdt
                
                prices["success"] = True
                prices["source"] = "binance"
                
                logger.info(f"Fetched crypto prices from Binance: BCH=£{prices['bitcoin-cash']:.2f}, BC2=£{prices['bellscoin']:.6f}, DGB=£{prices['digibyte']:.6f}, BTC=£{prices['bitcoin']:.2f}")
                return prices
            else:
                logger.warning("Binance API returned non-200 status")
                
    except Exception as e:
        logger.warning(f"Binance API failed: {str(e)}")
    
    # All APIs failed
    error_msg = "All crypto price APIs failed (CoinGecko, CoinCap, Binance)"
    logger.error(error_msg)
    
    async with AsyncSessionLocal() as session:
        event = Event(
            event_type="api_error",
            source="crypto_pricing",
            message=error_msg
        )
        session.add(event)
        await session.commit()
    
    prices["error"] = error_msg
    return prices


# This function is called by the scheduler, not exposed as an endpoint
async def update_crypto_prices_cache():
    """Background task to update cached crypto prices"""
    logger.info("Updating crypto price cache...")
    
    prices = await fetch_and_cache_crypto_prices()
    
    if prices["success"]:
        # Store in database
        async with AsyncSessionLocal() as session:
            for coin_id in ["bitcoin", "bitcoin-cash", "bellscoin", "digibyte"]:
                price_value = prices.get(coin_id, 0)
                if price_value > 0:
                    # Check if exists
                    result = await session.execute(
                        select(CryptoPrice).where(CryptoPrice.coin_id == coin_id)
                    )
                    cached_price = result.scalar_one_or_none()
                    
                    if cached_price:
                        cached_price.price_gbp = price_value
                        cached_price.source = prices["source"]
                        cached_price.updated_at = datetime.utcnow()
                    else:
                        new_price = CryptoPrice(
                            coin_id=coin_id,
                            price_gbp=price_value,
                            source=prices["source"]
                        )
                        session.add(new_price)
            
            await session.commit()
            logger.info(f"Crypto price cache updated from {prices['source']}")
    else:
        logger.warning(f"Failed to update crypto price cache: {prices.get('error')}")


@router.post("/trigger-aggregation")
async def trigger_telemetry_aggregation():
    """
    Manually trigger telemetry aggregation job.
    
    This is normally run daily at 00:05, but can be triggered manually for testing.
    Aggregates yesterday's telemetry into hourly and daily tables.
    """
    from core.scheduler import scheduler_service
    
    try:
        if scheduler_service and scheduler_service.scheduler:
            # Get the aggregation function directly
            job = scheduler_service.scheduler.get_job("aggregate_telemetry")
            if job:
                # Run the job immediately
                await scheduler_service._aggregate_telemetry()
                return {
                    "status": "success",
                    "message": "Telemetry aggregation triggered successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": "Aggregation job not found in scheduler"
                }
        else:
            return {
                "status": "error",
                "message": "Scheduler service not available"
            }
    except Exception as e:
        logger.error(f"Failed to trigger aggregation: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to trigger aggregation: {str(e)}"
        }


@router.get("/ai/status")
async def ai_status():
    """
    Stub endpoint for AI configuration status.
    
    TODO: Implement AI assistant functionality.
    For now, returns empty config to prevent 404 errors from frontend.
    """
    return {
        "enabled": False,
        "config": {
            "enabled": False,
            "provider": "openai",
            "model": "gpt-4o",
            "max_tokens": 1000
        }
    }

