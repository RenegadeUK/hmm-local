"""
Settings API endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx
import logging

from core.database import get_db, Miner, Pool, Telemetry, Event, AsyncSessionLocal, CryptoPrice
from core.config import app_config
from core.solopool import SolopoolService
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
        "topic_prefix": mqtt_config.get("topic_prefix", "miner"),
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


@router.get("/solopool/stats")
async def get_solopool_stats(db: AsyncSession = Depends(get_db)):
    """Get Solopool stats for all miners using Solopool pools (BCH, DGB, BTC, and XMR)"""
    # Check if Solopool integration is enabled
    if not app_config.get("solopool_enabled", False):
        return {"enabled": False, "bch_miners": [], "dgb_miners": [], "btc_miners": [], "xmr_miners": []}
    
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
    
    # For XMR, also include pool configurations (since we don't track XMR miners actively)
    xmr_pool_configs = []
    if xmr_pools and not xmr_stats_list:
        # If we have XMR pools configured but no active miners, create placeholder entries
        for pool_url, pool_obj in xmr_pools.items():
            username = SolopoolService.extract_username(pool_obj.user)
            xmr_pool_configs.append({
                "pool_url": pool_obj.url,
                "pool_port": pool_obj.port,
                "username": username,
                "coin": "XMR"
            })
    
    return {
        "enabled": True,
        "bch_miners": bch_stats_list,
        "dgb_miners": dgb_stats_list,
        "btc_miners": btc_stats_list,
        "xmr_pools": xmr_pool_configs,
        "xmr_miners": xmr_stats_list
    }


@router.get("/crypto-prices")
async def get_crypto_prices():
    """Return cached crypto prices (updated every 10 minutes by scheduler)"""
    prices = {
        "bitcoin-cash": 0,
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
                    'ids': 'bitcoin-cash,digibyte,bitcoin',
                    'vs_currencies': 'gbp'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                prices["bitcoin-cash"] = data.get("bitcoin-cash", {}).get("gbp", 0)
                prices["digibyte"] = data.get("digibyte", {}).get("gbp", 0)
                prices["bitcoin"] = data.get("bitcoin", {}).get("gbp", 0)
                prices["success"] = True
                prices["source"] = "coingecko"
                
                logger.info(f"Fetched crypto prices from CoinGecko: BCH=£{prices['bitcoin-cash']}, DGB=£{prices['digibyte']}, BTC=£{prices['bitcoin']}")
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
            # CoinCap uses different IDs: bitcoin-cash, digibyte, bitcoin
            bch_response = await client.get('https://api.coincap.io/v2/assets/bitcoin-cash')
            dgb_response = await client.get('https://api.coincap.io/v2/assets/digibyte')
            btc_response = await client.get('https://api.coincap.io/v2/assets/bitcoin')
            
            # Get GBP exchange rate
            gbp_response = await client.get('https://api.coincap.io/v2/rates/british-pound-sterling')
            
            if all(r.status_code == 200 for r in [bch_response, dgb_response, btc_response, gbp_response]):
                gbp_rate = float(gbp_response.json()["data"]["rateUsd"])
                
                bch_usd = float(bch_response.json()["data"]["priceUsd"])
                dgb_usd = float(dgb_response.json()["data"]["priceUsd"])
                btc_usd = float(btc_response.json()["data"]["priceUsd"])
                
                prices["bitcoin-cash"] = bch_usd / gbp_rate
                prices["digibyte"] = dgb_usd / gbp_rate
                prices["bitcoin"] = btc_usd / gbp_rate
                prices["success"] = True
                prices["source"] = "coincap"
                
                logger.info(f"Fetched crypto prices from CoinCap: BCH=£{prices['bitcoin-cash']:.2f}, DGB=£{prices['digibyte']:.6f}, BTC=£{prices['bitcoin']:.2f}")
                return prices
            else:
                logger.warning("CoinCap API returned non-200 status")
                
    except Exception as e:
        logger.warning(f"CoinCap API failed: {str(e)}")
    
    # Fallback to Binance API (convert via USDT then to GBP)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Binance provides direct GBP pairs for BTC
            btc_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCGBP')
            bch_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=BCHGBP')
            
            # DGB not on Binance with GBP, get USDT price and convert
            dgb_usdt_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=DGBUSDT')
            usdt_gbp_response = await client.get('https://api.binance.com/api/v3/ticker/price?symbol=GBPUSDT')
            
            if all(r.status_code == 200 for r in [btc_response, bch_response, dgb_usdt_response, usdt_gbp_response]):
                prices["bitcoin"] = float(btc_response.json()["price"])
                prices["bitcoin-cash"] = float(bch_response.json()["price"])
                
                dgb_usdt = float(dgb_usdt_response.json()["price"])
                gbp_usdt = float(usdt_gbp_response.json()["price"])
                prices["digibyte"] = dgb_usdt / gbp_usdt
                
                prices["success"] = True
                prices["source"] = "binance"
                
                logger.info(f"Fetched crypto prices from Binance: BCH=£{prices['bitcoin-cash']:.2f}, DGB=£{prices['digibyte']:.6f}, BTC=£{prices['bitcoin']:.2f}")
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
            for coin_id in ["bitcoin", "bitcoin-cash", "digibyte"]:
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
