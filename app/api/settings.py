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

from core.database import get_db, Miner, Pool, Telemetry, Event, AsyncSessionLocal, CryptoPrice, SupportXMRSnapshot
from core.config import app_config
from core.solopool import SolopoolService
from core.supportxmr import SupportXMRService
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter()


class MQTTSettings(BaseModel):
    enabled: bool
    broker: str
    port: int
    topic_prefix: str
    username: Optional[str] = ""
    password: Optional[str] = ""


@router.get("/mqtt")
async def get_mqtt_settings():
    """Get MQTT settings"""
    mqtt_config = app_config.get("mqtt", {})
    return {
        "enabled": mqtt_config.get("enabled", False),
        "broker": mqtt_config.get("broker", "localhost"),
        "port": mqtt_config.get("port", 1883),
        "topic_prefix": mqtt_config.get("topic_prefix", "miner_controller"),
        "username": mqtt_config.get("username", ""),
        "password": mqtt_config.get("password", "")
    }


@router.post("/mqtt")
async def save_mqtt_settings(settings: MQTTSettings):
    """Save MQTT settings"""
    app_config.set("mqtt.enabled", settings.enabled)
    app_config.set("mqtt.broker", settings.broker)
    app_config.set("mqtt.port", settings.port)
    app_config.set("mqtt.topic_prefix", settings.topic_prefix)
    app_config.set("mqtt.username", settings.username)
    app_config.set("mqtt.password", settings.password)
    app_config.save()
    
    return {
        "message": "MQTT settings saved successfully"
    }


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


class XMRAgentsSettings(BaseModel):
    enabled: bool


@router.get("/xmr_agents")
async def get_xmr_agents_settings():
    """Get XMR Agents settings"""
    agents_config = app_config.get("xmr_agents", {})
    return {
        "enabled": agents_config.get("enabled", False)
    }


@router.post("/xmr_agents")
async def save_xmr_agents_settings(settings: XMRAgentsSettings):
    """Save XMR Agents settings"""
    app_config.set("xmr_agents.enabled", settings.enabled)
    app_config.save()
    
    # Log the change
    async with AsyncSessionLocal() as db:
        event = Event(
            event_type="info",
            source="api",
            message=f"XMR Agents {'enabled' if settings.enabled else 'disabled'}"
        )
        db.add(event)
        await db.commit()
    
    return {
        "message": "XMR Agents settings saved successfully"
    }


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
    from core.braiins import BraiinsPoolService
    
    # Check if Braiins integration is enabled
    if not app_config.get("braiins_enabled", False):
        return {"enabled": False, "stats": None}
    
    api_token = app_config.get("braiins_api_token", "")
    if not api_token:
        return {"enabled": False, "stats": None, "error": "No API token configured"}
    
    # Check if any miners are using Braiins Pool
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    braiins_pools = [p for p in all_pools if BraiinsPoolService.is_braiins_pool(p.url, p.port)]
    
    if not braiins_pools:
        return {"enabled": True, "stats": None, "miners_using": 0}
    
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
    
    # Only fetch stats if miners are actually using Braiins Pool
    if miners_using_braiins == 0:
        return {"enabled": True, "stats": None, "miners_using": 0}
    
    # Get username from the first Braiins pool (they should all have same username)
    braiins_username = ""
    if braiins_pools:
        # Extract username from pool user (format: username.workername or just username)
        pool_user = braiins_pools[0].user
        braiins_username = pool_user.split('.')[0] if pool_user else ""
    
    # Fetch data from Braiins API
    workers_data = await BraiinsPoolService.get_workers(api_token)
    profile_data = await BraiinsPoolService.get_profile(api_token)
    rewards_data = await BraiinsPoolService.get_rewards(api_token)
    
    stats = BraiinsPoolService.format_stats_summary(workers_data, profile_data, rewards_data)
    
    return {
        "enabled": True,
        "miners_using": miners_using_braiins,
        "username": braiins_username,
        "stats": stats
    }


class SupportXMRSettings(BaseModel):
    enabled: bool


@router.get("/supportxmr")
async def get_supportxmr_settings():
    """Get SupportXMR pool integration settings"""
    return {
        "enabled": app_config.get("supportxmr_enabled", False)
    }


@router.post("/supportxmr")
async def save_supportxmr_settings(settings: SupportXMRSettings):
    """Save SupportXMR pool integration settings"""
    app_config.set("supportxmr_enabled", settings.enabled)
    app_config.save()
    
    return {
        "message": "SupportXMR settings saved",
        "enabled": settings.enabled
    }


@router.get("/supportxmr/stats")
async def get_supportxmr_stats(db: AsyncSession = Depends(get_db)):
    """Get SupportXMR stats - returns array of wallet stats for multiple wallets"""
    # Check if SupportXMR integration is enabled
    if not app_config.get("supportxmr_enabled", False):
        return {"enabled": False, "wallets": []}
    
    # Check if SupportXMR pool is configured
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    supportxmr_pools = [p for p in all_pools if SupportXMRService.is_supportxmr_pool(p.url, p.port)]
    
    if not supportxmr_pools:
        return {"enabled": True, "wallets": []}
    
    # Process each unique wallet
    wallet_stats_list = []
    processed_addresses = set()
    
    for pool in supportxmr_pools:
        wallet_address = SupportXMRService.extract_address(pool.user)
        
        if not wallet_address or wallet_address in processed_addresses:
            continue
        
        processed_addresses.add(wallet_address)
        
        # Fetch data from SupportXMR API
        stats_data = await SupportXMRService.get_miner_stats(wallet_address)
        payments_data = await SupportXMRService.get_miner_payments(wallet_address)
        identifiers_data = await SupportXMRService.get_miner_identifiers(wallet_address)
        
        if not stats_data:
            continue
        
        # Count workers (identifiers)
        worker_count = 0
        if identifiers_data and isinstance(identifiers_data, list):
            worker_count = len(identifiers_data)
        
        # Calculate 24-hour earnings delta
        current_amount_due_xmr = float(SupportXMRService.format_xmr(stats_data.get("amtDue", 0)))
        current_amount_paid_xmr = float(SupportXMRService.format_xmr(stats_data.get("amtPaid", 0)))
        
        # Get snapshot from 24 hours ago
        from datetime import datetime, timedelta
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        
        snapshot_result = await db.execute(
            select(SupportXMRSnapshot)
            .where(SupportXMRSnapshot.wallet_address == wallet_address)
            .where(SupportXMRSnapshot.timestamp >= twenty_four_hours_ago)
            .order_by(SupportXMRSnapshot.timestamp.asc())
            .limit(1)
        )
        old_snapshot = snapshot_result.scalar_one_or_none()
        
        if old_snapshot:
            current_total = current_amount_due_xmr + current_amount_paid_xmr
            old_total = old_snapshot.amount_due + old_snapshot.amount_paid
            today_rewards = max(0, current_total - old_total)
        else:
            today_rewards = 0
        
        # Store current snapshot (limit to one per hour to avoid bloat)
        recent_snapshot = await db.execute(
            select(SupportXMRSnapshot)
            .where(SupportXMRSnapshot.wallet_address == wallet_address)
            .where(SupportXMRSnapshot.timestamp >= datetime.utcnow() - timedelta(hours=1))
            .limit(1)
        )
        
        if not recent_snapshot.scalar_one_or_none():
            new_snapshot = SupportXMRSnapshot(
                wallet_address=wallet_address,
                amount_due=current_amount_due_xmr,
                amount_paid=current_amount_paid_xmr,
                hashrate=stats_data.get("hash", 0),
                valid_shares=stats_data.get("validShares", 0),
                invalid_shares=stats_data.get("invalidShares", 0),
                timestamp=datetime.utcnow()
            )
            db.add(new_snapshot)
            await db.commit()
        
        # Add wallet stats to list
        wallet_stats_list.append({
            "address": wallet_address,
            "worker_count": worker_count,
            "hashrate": SupportXMRService.format_hashrate(stats_data.get("hash", 0)),
            "valid_shares": stats_data.get("validShares", 0),
            "invalid_shares": stats_data.get("invalidShares", 0),
            "amount_due": SupportXMRService.format_xmr(stats_data.get("amtDue", 0)),
            "amount_paid": SupportXMRService.format_xmr(stats_data.get("amtPaid", 0)),
            "today_rewards": f"{today_rewards:.6f}"
        })
    
    return {
        "enabled": True,
        "wallets": wallet_stats_list
    }


@router.get("/solopool/stats")
async def get_solopool_stats(db: AsyncSession = Depends(get_db)):
    """Get Solopool stats for all miners using Solopool pools (BCH, DGB, BTC, and XMR)"""
    # Check if Solopool integration is enabled
    if not app_config.get("solopool_enabled", False):
        return {"enabled": False, "strategy_enabled": False, "active_target": None, "bch_miners": [], "dgb_miners": [], "btc_miners": [], "xmr_pools": [], "xmr_miners": []}
    
    # Check if Agile Solo Strategy is enabled
    from core.database import AgileStrategy
    from core.agile_solo_strategy import PriceBand
    
    strategy_result = await db.execute(select(AgileStrategy))
    strategy = strategy_result.scalar_one_or_none()
    strategy_enabled = strategy and strategy.enabled
    current_band = strategy.current_price_band if strategy else None
    
    # Map price band to active target coin
    active_target = None
    if strategy_enabled and current_band:
        if current_band in [PriceBand.DGB_HIGH, PriceBand.DGB_MED, PriceBand.DGB_LOW]:
            active_target = "DGB"
        elif current_band == PriceBand.BCH:
            active_target = "BCH"
        elif current_band == PriceBand.BTC:
            active_target = "BTC"
        # OFF band means all grayed out (active_target stays None)
    
    # Get all pools
    pool_result = await db.execute(select(Pool))
    all_pools = pool_result.scalars().all()
    
    bch_pools = {}
    dgb_pools = {}
    btc_pools = {}
    xmr_pools = {}
    for pool in all_pools:
        if SolopoolService.is_solopool_bch_pool(pool.url, pool.port):
            bch_pools[pool.url] = pool
        elif SolopoolService.is_solopool_dgb_pool(pool.url, pool.port):
            dgb_pools[pool.url] = pool
        elif SolopoolService.is_solopool_btc_pool(pool.url, pool.port):
            btc_pools[pool.url] = pool
        elif SolopoolService.is_solopool_xmr_pool(pool.url, pool.port):
            xmr_pools[pool.url] = pool
    
    if not bch_pools and not dgb_pools and not btc_pools and not xmr_pools:
        return {"enabled": True, "bch_miners": [], "dgb_miners": [], "btc_miners": [], "xmr_pools": [], "xmr_miners": []}
    
    # Fetch network/pool stats for ETTB calculation
    bch_network_stats = await SolopoolService.get_bch_pool_stats() if bch_pools else None
    dgb_network_stats = await SolopoolService.get_dgb_pool_stats() if dgb_pools else None
    btc_network_stats = await SolopoolService.get_btc_pool_stats() if btc_pools else None
    xmr_network_stats = await SolopoolService.get_xmr_pool_stats() if xmr_pools else None
    
    # Get all enabled miners
    miner_result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = miner_result.scalars().all()
    
    bch_stats_list = []
    dgb_stats_list = []
    btc_stats_list = []
    xmr_stats_list = []
    bch_processed_usernames = set()
    dgb_processed_usernames = set()
    btc_processed_usernames = set()
    xmr_processed_usernames = set()
    
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
        
        # Check XMR pools
        matching_pool = None
        for pool_url, pool_obj in xmr_pools.items():
            if pool_url in pool_in_use:
                matching_pool = pool_obj
                break
        
        if matching_pool:
            username = SolopoolService.extract_username(matching_pool.user)
            if username not in xmr_processed_usernames:
                xmr_processed_usernames.add(username)
                xmr_stats = await SolopoolService.get_xmr_account_stats(username)
                if xmr_stats:
                    formatted_stats = SolopoolService.format_stats_summary(xmr_stats)
                    # Calculate ETTB (XMR block time: 120 seconds)
                    if xmr_network_stats:
                        network_hashrate = xmr_network_stats.get("stats", {}).get("hashrate", 0)
                        user_hashrate = formatted_stats.get("hashrate_raw", 0)
                        ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 120)
                        formatted_stats["ettb"] = ettb
                        formatted_stats["network_hashrate"] = network_hashrate
                    
                    xmr_stats_list.append({
                        "miner_id": miner.id,
                        "miner_name": miner.name,
                        "pool_url": matching_pool.url,
                        "pool_port": matching_pool.port,
                        "username": username,
                        "coin": "XMR",
                        "stats": formatted_stats
                    })
    
    # For XMR, fetch stats directly from pool config (since we don't track XMR miners actively)
    # If no active miners were found using XMR pools, fetch stats for all configured XMR pools
    if xmr_pools and not xmr_stats_list:
        for pool_url, pool_obj in xmr_pools.items():
            username = SolopoolService.extract_username(pool_obj.user)
            if username not in xmr_processed_usernames:
                xmr_processed_usernames.add(username)
                xmr_stats = await SolopoolService.get_xmr_account_stats(username)
                if xmr_stats:
                    formatted_stats = SolopoolService.format_stats_summary(xmr_stats)
                    # Calculate ETTB (XMR block time: 120 seconds)
                    if xmr_network_stats:
                        network_hashrate = xmr_network_stats.get("stats", {}).get("hashrate", 0)
                        user_hashrate = formatted_stats.get("hashrate_raw", 0)
                        ettb = SolopoolService.calculate_ettb(network_hashrate, user_hashrate, 120)
                        formatted_stats["ettb"] = ettb
                        formatted_stats["network_hashrate"] = network_hashrate
                    
                    xmr_stats_list.append({
                        "miner_id": None,
                        "miner_name": None,
                        "pool_url": pool_obj.url,
                        "pool_port": pool_obj.port,
                        "username": username,
                        "coin": "XMR",
                        "stats": formatted_stats
                    })
    
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
    
    # Sort: strategy pools first (DGB → BCH → BTC order matching LOW → MED → HIGH)
    def sort_key(entry):
        if entry.get("is_strategy_pool"):
            coin = entry.get("coin", "")
            if coin == "DGB":
                return (0, 0)  # First (LOW)
            elif coin == "BCH":
                return (0, 1)  # Second (MED)
            elif coin == "BTC":
                return (0, 2)  # Third (HIGH)
        return (1, entry.get("coin", ""))  # Other pools after
    
    dgb_stats_list.sort(key=sort_key)
    btc_stats_list.sort(key=sort_key)
    bch_stats_list.sort(key=sort_key)
    
    return {
        "enabled": True,
        "strategy_enabled": strategy_enabled,
        "active_target": active_target,
        "bch_miners": bch_stats_list,
        "dgb_miners": dgb_stats_list,
        "btc_miners": btc_stats_list,
        "xmr_pools": [],
        "xmr_miners": xmr_stats_list
    }


@router.get("/crypto-prices")
async def get_crypto_prices():
    """Return cached crypto prices (updated every 10 minutes by scheduler)"""
    prices = {
        "bitcoin-cash": 0,
        "digibyte": 0,
        "bitcoin": 0,
        "monero": 0,
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
            prices["digibyte"] = cached_prices.get("digibyte").price_gbp if "digibyte" in cached_prices else 0
            prices["monero"] = cached_prices.get("monero").price_gbp if "monero" in cached_prices else 0
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
                    'ids': 'bitcoin-cash,digibyte,bitcoin,monero',
                    'vs_currencies': 'gbp'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                prices["bitcoin-cash"] = data.get("bitcoin-cash", {}).get("gbp", 0)
                prices["digibyte"] = data.get("digibyte", {}).get("gbp", 0)
                prices["bitcoin"] = data.get("bitcoin", {}).get("gbp", 0)
                prices["monero"] = data.get("monero", {}).get("gbp", 0)
                prices["success"] = True
                prices["source"] = "coingecko"
                
                logger.info(f"Fetched crypto prices from CoinGecko: BCH=£{prices['bitcoin-cash']}, DGB=£{prices['digibyte']}, BTC=£{prices['bitcoin']}, XMR=£{prices['monero']}")
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
            # CoinCap uses different IDs: bitcoin-cash, digibyte, bitcoin, monero
            bch_response = await client.get('https://api.coincap.io/v2/assets/bitcoin-cash')
            dgb_response = await client.get('https://api.coincap.io/v2/assets/digibyte')
            btc_response = await client.get('https://api.coincap.io/v2/assets/bitcoin')
            xmr_response = await client.get('https://api.coincap.io/v2/assets/monero')
            
            # Get GBP exchange rate
            gbp_response = await client.get('https://api.coincap.io/v2/rates/british-pound-sterling')
            
            if all(r.status_code == 200 for r in [bch_response, dgb_response, btc_response, xmr_response, gbp_response]):
                gbp_rate = float(gbp_response.json()["data"]["rateUsd"])
                
                bch_usd = float(bch_response.json()["data"]["priceUsd"])
                dgb_usd = float(dgb_response.json()["data"]["priceUsd"])
                btc_usd = float(btc_response.json()["data"]["priceUsd"])
                xmr_usd = float(xmr_response.json()["data"]["priceUsd"])
                
                prices["bitcoin-cash"] = bch_usd / gbp_rate
                prices["digibyte"] = dgb_usd / gbp_rate
                prices["bitcoin"] = btc_usd / gbp_rate
                prices["monero"] = xmr_usd / gbp_rate
                prices["success"] = True
                prices["source"] = "coincap"
                
                logger.info(f"Fetched crypto prices from CoinCap: BCH=£{prices['bitcoin-cash']:.2f}, DGB=£{prices['digibyte']:.6f}, BTC=£{prices['bitcoin']:.2f}, XMR=£{prices['monero']:.2f}")
                return prices
            else:
                logger.warning("CoinCap API returned non-200 status")
                
    except Exception as e:
        logger.warning(f"CoinCap API failed: {str(e)}")
    
    # Fallback to Binance API (convert via USDT then to GBP)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Binance provides direct GBP pairs for BTC, BCH, XMR
            btc_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCGBP')
            bch_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=BCHGBP')
            xmr_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=XMRGBP')
            
            # DGB not on Binance with GBP, get USDT price and convert
            dgb_usdt_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=DGBUSDT')
            usdt_gbp_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=GBPUSDT')
            
            if all(r.status_code == 200 for r in [btc_response, bch_response, xmr_response, dgb_usdt_response, usdt_gbp_response]):
                prices["bitcoin"] = float(btc_response.json()["price"])
                prices["bitcoin-cash"] = float(bch_response.json()["price"])
                prices["monero"] = float(xmr_response.json()["price"])
                
                dgb_usdt = float(dgb_usdt_response.json()["price"])
                gbp_usdt = float(usdt_gbp_response.json()["price"])
                prices["digibyte"] = dgb_usdt / gbp_usdt
                
                prices["success"] = True
                prices["source"] = "binance"
                
                logger.info(f"Fetched crypto prices from Binance: BCH=£{prices['bitcoin-cash']:.2f}, DGB=£{prices['digibyte']:.6f}, BTC=£{prices['bitcoin']:.2f}, XMR=£{prices['monero']:.2f}")
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
            for coin_id in ["bitcoin", "bitcoin-cash", "digibyte", "monero"]:
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


# ============================================================================
# CKPool Analytics Backfill
# ============================================================================

@router.get("/ckpool/backfill-preview")
async def preview_ckpool_backfill(db: AsyncSession = Depends(get_db)):
    """
    Preview what would be backfilled without actually doing it.
    Shows count of complete vs incomplete blocks.
    """
    from sqlalchemy import text
    
    try:
        # Total accepted blocks
        result = await db.execute(text("""
            SELECT COUNT(*) FROM ckpool_blocks WHERE block_accepted = 1
        """))
        total_accepted = result.scalar()
        
        # Complete blocks (has height AND hash)
        result = await db.execute(text("""
            SELECT COUNT(*) FROM ckpool_blocks 
            WHERE block_accepted = 1 
            AND block_height IS NOT NULL 
            AND block_hash IS NOT NULL
        """))
        complete_blocks = result.scalar()
        
        # Incomplete blocks
        incomplete_blocks = total_accepted - complete_blocks
        
        # Sample of complete blocks with pool names
        result = await db.execute(text("""
            SELECT cb.block_height, cb.block_hash, cb.timestamp, p.name
            FROM ckpool_blocks cb
            JOIN pools p ON cb.pool_id = p.id
            WHERE cb.block_accepted = 1 
            AND cb.block_height IS NOT NULL 
            AND cb.block_hash IS NOT NULL
            ORDER BY cb.timestamp DESC
            LIMIT 5
        """))
        sample_blocks = [{"height": r[0], "hash": r[1], "timestamp": str(r[2]), "pool_name": r[3]} for r in result.fetchall()]
        
        # Check metrics table
        result = await db.execute(text("""
            SELECT COUNT(*) FROM ckpool_block_metrics
        """))
        metrics_count = result.scalar()
        
        result = await db.execute(text("""
            SELECT coin, COUNT(*) as count
            FROM ckpool_block_metrics
            GROUP BY coin
        """))
        metrics_by_coin = {r[0]: r[1] for r in result.fetchall()}
        
        return {
            "total_accepted_blocks": total_accepted,
            "complete_blocks": complete_blocks,
            "incomplete_blocks": incomplete_blocks,
            "can_migrate": complete_blocks > 0,
            "sample_blocks": sample_blocks,
            "metrics_table_count": metrics_count,
            "metrics_by_coin": metrics_by_coin
        }
    except Exception as e:
        logger.error(f"Preview failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/ckpool/backfill-metrics")
async def backfill_ckpool_metrics():
    """
    One-time backfill: Copy accepted blocks from ckpool_blocks to ckpool_block_metrics.
    Sets effort_percent=100.0 for historical blocks.
    Extracts coin from pool name (DGB, BCH, BTC).
    Safe to run multiple times (skips duplicates by block_hash).
    """
    from core.migrations import backfill_ckpool_metrics
    
    try:
        await backfill_ckpool_metrics()
        return {
            "success": True,
            "message": "Backfill completed successfully. Check container logs for details."
        }
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/ckpool/blocks-data")
async def get_ckpool_blocks_data(
    db: AsyncSession = Depends(get_db)
):
    """Get all blocks from ckpool_blocks table for debugging"""
    try:
        from sqlalchemy import select
        from core.database import CKPoolBlock, Pool
        
        result = await db.execute(
            select(CKPoolBlock, Pool)
            .join(Pool, CKPoolBlock.pool_id == Pool.id)
            .order_by(CKPoolBlock.timestamp.desc())
        )
        rows = result.all()
        
        return {
            "total": len(rows),
            "blocks": [
                {
                    "id": b.id,
                    "pool_id": b.pool_id,
                    "pool_name": p.name,
                    "coin": p.name.split()[-1] if p.name else "UNKNOWN",  # Extract coin from pool name
                    "block_height": b.block_height,
                    "block_hash": b.block_hash,
                    "timestamp": b.timestamp.isoformat(),
                    "block_accepted": b.block_accepted,
                    "confirmed_reward_coins": b.confirmed_reward_coins,
                    "confirmed_from_explorer": b.confirmed_from_explorer,
                }
                for b, p in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ckpool/update-block")
async def update_ckpool_block(
    block_id: int,
    block_height: int,
    block_hash: str,
    confirmed_reward_coins: float,
    db: AsyncSession = Depends(get_db)
):
    """Update a ckpool_blocks entry with missing height/hash/reward data"""
    try:
        from sqlalchemy import select, update
        from core.database import CKPoolBlock
        
        # Check if block exists
        result = await db.execute(
            select(CKPoolBlock).where(CKPoolBlock.id == block_id)
        )
        block = result.scalar_one_or_none()
        
        if not block:
            raise HTTPException(status_code=404, detail=f"Block {block_id} not found")
        
        if not block.block_accepted:
            raise HTTPException(status_code=400, detail=f"Block {block_id} was not accepted, cannot update")
        
        # Update the block
        await db.execute(
            update(CKPoolBlock)
            .where(CKPoolBlock.id == block_id)
            .values(
                block_height=block_height,
                block_hash=block_hash,
                confirmed_reward_coins=confirmed_reward_coins,
                confirmed_from_explorer=True
            )
        )
        await db.commit()
        
        return {"success": True, "message": f"Updated block {block_id} with height {block_height}"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ckpool/update-metrics-effort")
async def update_ckpool_metrics_effort(
    block_height: int,
    effort_percent: float,
    db: AsyncSession = Depends(get_db)
):
    """Update effort_percent for a block in ckpool_block_metrics (for manual corrections)"""
    try:
        from sqlalchemy import update
        from core.database import CKPoolBlockMetrics
        
        result = await db.execute(
            update(CKPoolBlockMetrics)
            .where(CKPoolBlockMetrics.block_height == block_height)
            .values(effort_percent=effort_percent)
        )
        await db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Block {block_height} not found in metrics")
        
        return {"success": True, "message": f"Updated block {block_height} effort to {effort_percent}%"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ckpool/update-metrics-time")
async def update_ckpool_metrics_time(
    block_height: int,
    time_to_block_seconds: int,
    db: AsyncSession = Depends(get_db)
):
    """Update time_to_block_seconds for a block in ckpool_block_metrics"""
    try:
        from sqlalchemy import update
        from core.database import CKPoolBlockMetrics
        
        result = await db.execute(
            update(CKPoolBlockMetrics)
            .where(CKPoolBlockMetrics.block_height == block_height)
            .values(time_to_block_seconds=time_to_block_seconds)
        )
        await db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Block {block_height} not found in metrics")
        
        return {"success": True, "message": f"Updated block {block_height} time_to_block to {time_to_block_seconds}s"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ckpool/metrics-data")
async def get_ckpool_metrics_data(db: AsyncSession = Depends(get_db)):
    """View current data in ckpool_block_metrics table"""
    from sqlalchemy import text
    
    try:
        result = await db.execute(text("""
            SELECT 
                m.id, m.coin, m.block_height, m.block_hash,
                m.timestamp, m.effort_percent, m.time_to_block_seconds,
                m.confirmed_reward_coins, p.name as pool_name
            FROM ckpool_block_metrics m
            JOIN pools p ON m.pool_id = p.id
            ORDER BY m.timestamp DESC
            LIMIT 20
        """))
        
        blocks = [{
            "id": r[0],
            "coin": r[1],
            "block_height": r[2],
            "block_hash": r[3],
            "timestamp": str(r[4]),
            "effort_percent": r[5],
            "time_to_block_seconds": r[6],
            "confirmed_reward_coins": r[7],
            "pool_name": r[8]
        } for r in result.fetchall()]
        
        return {"blocks": blocks, "count": len(blocks)}
    except Exception as e:
        logger.error(f"Failed to get metrics data: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/ckpool/prune-preview")
async def preview_ckpool_prune(db: AsyncSession = Depends(get_db)):
    """Preview what would be deleted by pruning (without actually deleting)"""
    from sqlalchemy import text
    from datetime import datetime, timedelta
    
    try:
        # Non-accepted blocks older than 30 days
        cutoff_30d = datetime.utcnow() - timedelta(days=30)
        result = await db.execute(text("""
            SELECT COUNT(*) FROM ckpool_blocks 
            WHERE block_accepted = 0 
            AND timestamp < :cutoff
        """), {"cutoff": cutoff_30d})
        non_accepted_old = result.scalar()
        
        # Accepted blocks (should NEVER be deleted)
        result = await db.execute(text("""
            SELECT COUNT(*) FROM ckpool_blocks WHERE block_accepted = 1
        """))
        accepted_total = result.scalar()
        
        # Metrics older than 12 months
        cutoff_12m = datetime.utcnow() - timedelta(days=365)
        result = await db.execute(text("""
            SELECT COUNT(*) FROM ckpool_block_metrics 
            WHERE timestamp < :cutoff
        """), {"cutoff": cutoff_12m})
        metrics_old = result.scalar()
        
        # Total metrics
        result = await db.execute(text("""
            SELECT COUNT(*) FROM ckpool_block_metrics
        """))
        metrics_total = result.scalar()
        
        return {
            "ckpool_blocks": {
                "non_accepted_to_delete": non_accepted_old,
                "accepted_to_keep": accepted_total,
                "cutoff_date": str(cutoff_30d)
            },
            "ckpool_block_metrics": {
                "old_to_delete": metrics_old,
                "total_metrics": metrics_total,
                "cutoff_date": str(cutoff_12m)
            }
        }
    except Exception as e:
        logger.error(f"Prune preview failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/ckpool/prune-now")
async def manual_prune_ckpool(db: AsyncSession = Depends(get_db)):
    """Manually trigger CKPool pruning (for testing)"""
    from sqlalchemy import text
    from datetime import datetime, timedelta
    
    try:
        # Prune non-accepted blocks older than 30 days
        cutoff_30d = datetime.utcnow() - timedelta(days=30)
        result = await db.execute(text("""
            DELETE FROM ckpool_blocks 
            WHERE block_accepted = 0 
            AND timestamp < :cutoff
        """), {"cutoff": cutoff_30d})
        await db.commit()
        deleted_blocks = result.rowcount
        
        # Prune metrics older than 12 months
        cutoff_12m = datetime.utcnow() - timedelta(days=365)
        result = await db.execute(text("""
            DELETE FROM ckpool_block_metrics 
            WHERE timestamp < :cutoff
        """), {"cutoff": cutoff_12m})
        await db.commit()
        deleted_metrics = result.rowcount
        
        return {
            "success": True,
            "deleted_non_accepted_blocks": deleted_blocks,
            "deleted_old_metrics": deleted_metrics
        }
    except Exception as e:
        logger.error(f"Manual prune failed: {e}", exc_info=True)
        await db.rollback()
        return {
            "success": False,
            "error": str(e)
        }

