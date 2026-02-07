"""
Energy Optimization Service
"""
from datetime import datetime, timedelta
from urllib.parse import urlparse
from typing import Dict, List, Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Miner, EnergyPrice, Telemetry, Pool
from core.config import app_config


async def get_current_energy_price(db: AsyncSession) -> Optional[EnergyPrice]:
    """
    Get the current energy price for the configured region
    
    Args:
        db: Database session
    
    Returns:
        Current EnergyPrice object or None if not available
    """
    region = app_config.get("octopus_agile.region", "H")
    now = datetime.utcnow()
    
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from <= now)
        .where(EnergyPrice.valid_to > now)
        .limit(1)
    )
    return result.scalar_one_or_none()


class EnergyOptimizationService:
    """Service for energy optimization and profitability calculations"""
    
    # Coin algorithm types
    ALGO_SHA256 = "SHA256"
    
    # Pool to coin mapping
    POOL_COINS = {
        "bch.solopool.org": {"coin": "BCH", "algo": ALGO_SHA256, "block_reward": 3.125, "block_time": 600},
        "dgb.solopool.org": {"coin": "DGB", "algo": ALGO_SHA256, "block_reward": 277.376, "block_time": 15},
        "btc.solopool.org": {"coin": "BTC", "algo": ALGO_SHA256, "block_reward": 3.125, "block_time": 600},
        "bc2.solopool.org": {"coin": "BC2", "algo": ALGO_SHA256, "block_reward": 0.0, "block_time": 600},
        "pool.braiins.com": {"coin": "BTC", "algo": ALGO_SHA256, "block_reward": 3.125, "block_time": 600},
    }

    @staticmethod
    def _parse_pool_host_port(pool_in_use: str) -> tuple[Optional[str], Optional[int]]:
        if not pool_in_use:
            return None, None

        pool_str = pool_in_use.strip()
        if "://" not in pool_str:
            pool_str = f"stratum+tcp://{pool_str}"

        parsed = urlparse(pool_str)
        host = parsed.hostname
        port = parsed.port

        if not host:
            cleaned = pool_in_use
            if "@" in cleaned:
                cleaned = cleaned.split("@", 1)[-1]
            if ":" in cleaned:
                host_part, port_part = cleaned.rsplit(":", 1)
                host = host_part.strip() or None
                try:
                    port = int(port_part)
                except ValueError:
                    port = None

        return host, port

    @staticmethod
    def _detect_coin_from_pool(pool_in_use: str) -> Optional[Dict[str, Any]]:
        """
        Detect coin from pool name/URL.
        Note: This is a simplified fallback. Proper implementation should query Pool table for coin.
        """
        if not pool_in_use:
            return None

        pool_lower = pool_in_use.lower()
        
        # Check common pool patterns
        if "braiins" in pool_lower or "slushpool" in pool_lower:
            return {"coin": "BTC", "algo": EnergyOptimizationService.ALGO_SHA256, "block_reward": 3.125, "block_time": 600}
        if "bch" in pool_lower:
            return {"coin": "BCH", "algo": EnergyOptimizationService.ALGO_SHA256, "block_reward": 3.125, "block_time": 600}
        if "dgb" in pool_lower:
            return {"coin": "DGB", "algo": EnergyOptimizationService.ALGO_SHA256, "block_reward": 277.376, "block_time": 15}
        if "bc2" in pool_lower:
            return {"coin": "BC2", "algo": EnergyOptimizationService.ALGO_SHA256, "block_reward": 0.0, "block_time": 600}
        if "btc" in pool_lower:
            return {"coin": "BTC", "algo": EnergyOptimizationService.ALGO_SHA256, "block_reward": 3.125, "block_time": 600}

        if "solopool.org" in pool_lower:
            # Default to DGB for generic solopool
            return {"coin": "DGB", "algo": EnergyOptimizationService.ALGO_SHA256, "block_reward": 277.376, "block_time": 15}

        return None


        return None
    
    @staticmethod
    async def calculate_profitability(
        miner_id: int,
        db: AsyncSession,
        hours: int = 24,
        coin_prices: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Calculate mining profitability (revenue - energy cost)
        
        Args:
            miner_id: Miner ID
            db: Database session
            hours: Time period in hours
            coin_prices: Dict of coin prices in GBP (e.g. {"BTC": 75000, "BCH": 350})
        
        Returns:
            Dict with profitability metrics
        """
        # Get miner
        result = await db.execute(select(Miner).where(Miner.id == miner_id))
        miner = result.scalar_one_or_none()
        
        if not miner:
            return {"error": "Miner not found"}
        
        # Get telemetry
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner_id)
            .where(Telemetry.timestamp >= cutoff)
            .order_by(Telemetry.timestamp.desc())
        )
        telemetry_data = result.scalars().all()
        
        if not telemetry_data:
            return {"error": "No telemetry data"}
        
        # Calculate energy cost
        energy_cost = await EnergyOptimizationService._calculate_energy_cost(
            miner_id, db, hours, telemetry_data
        )
        
        # Get current pool
        latest = telemetry_data[0]
        pool_in_use = latest.pool_in_use
        
        if not pool_in_use:
            return {
                "miner_id": miner_id,
                "miner_name": miner.name,
                "period_hours": hours,
                "energy_cost_gbp": energy_cost,
                "revenue_gbp": 0,
                "profit_gbp": -energy_cost,
                "roi_percent": -100,
                "error": "No active pool"
            }
        
        # Determine coin being mined
        coin_info = EnergyOptimizationService._detect_coin_from_pool(pool_in_use)

        if not coin_info:
            for pool_domain, info in EnergyOptimizationService.POOL_COINS.items():
                if pool_domain in pool_in_use:
                    coin_info = info
                    break
        
        if not coin_info:
            return {
                "miner_id": miner_id,
                "miner_name": miner.name,
                "period_hours": hours,
                "energy_cost_gbp": energy_cost,
                "revenue_gbp": 0,
                "profit_gbp": -energy_cost,
                "roi_percent": -100,
                "error": "Unknown pool/coin"
            }
        
        # Calculate expected revenue
        avg_hashrate = sum(t.hashrate for t in telemetry_data if t.hashrate) / len(telemetry_data)
        
        # For pool mining (Braiins), use historical rewards if available
        # For solo mining, calculate theoretical earnings
        revenue_gbp = 0
        
        if coin_prices and coin_info["coin"] in coin_prices:
            coin_price = coin_prices[coin_info["coin"]]
            
            # Theoretical calculation for solo mining
            # This is highly probabilistic - actual earnings vary greatly
            if "solopool" in pool_in_use.lower():
                # Solo mining - very low probability
                # Calculate expected value but note it's theoretical
                revenue_gbp = 0  # Solo mining revenue is too variable to estimate
            else:
                # Pool mining - can estimate based on hashrate share
                # This is simplified - real calculation would need pool stats
                revenue_gbp = 0  # Requires pool API data
        
        profit_gbp = revenue_gbp - energy_cost
        roi_percent = ((profit_gbp / energy_cost) * 100) if energy_cost > 0 else 0
        
        return {
            "miner_id": miner_id,
            "miner_name": miner.name,
            "coin": coin_info["coin"],
            "period_hours": hours,
            "avg_hashrate_ghs": round(avg_hashrate, 2),
            "energy_cost_gbp": round(energy_cost, 2),
            "revenue_gbp": round(revenue_gbp, 2),
            "profit_gbp": round(profit_gbp, 2),
            "roi_percent": round(roi_percent, 2),
            "note": "Solo mining revenue is probabilistic and not estimated"
        }
    
    @staticmethod
    async def _calculate_energy_cost(
        miner_id: int,
        db: AsyncSession,
        hours: int,
        telemetry_data: List
    ) -> float:
        """Calculate energy cost in GBP for given period"""
        region = app_config.get("octopus_agile.region", "H")
        
        total_cost_pence = 0
        
        for telem in telemetry_data:
            if not telem.power_watts or telem.power_watts <= 0:
                continue
            
            # Find energy price for this timestamp
            result = await db.execute(
                select(EnergyPrice)
                .where(EnergyPrice.region == region)
                .where(EnergyPrice.valid_from <= telem.timestamp)
                .where(EnergyPrice.valid_to > telem.timestamp)
                .limit(1)
            )
            price = result.scalar_one_or_none()
            
            if price:
                interval_hours = 30 / 3600  # 30 second telemetry interval
                energy_kwh = (telem.power_watts / 1000) * interval_hours
                total_cost_pence += energy_kwh * price.price_pence
        
        return total_cost_pence / 100  # Convert to GBP
    
    @staticmethod
    async def get_price_forecast(
        db: AsyncSession,
        hours_ahead: int = 24
    ) -> List[Dict[str, Any]]:
        """Get energy price forecast for next N hours"""
        region = app_config.get("octopus_agile.region", "H")
        now = datetime.utcnow()
        end_time = now + timedelta(hours=hours_ahead)
        
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from >= now)
            .where(EnergyPrice.valid_from < end_time)
            .order_by(EnergyPrice.valid_from)
        )
        prices = result.scalars().all()
        
        return [
            {
                "timestamp": p.valid_from.isoformat(),
                "price_pence": p.price_pence,
                "is_cheap": p.price_pence < 10,  # Below 10p/kWh
                "is_expensive": p.price_pence > 25  # Above 25p/kWh
            }
            for p in prices
        ]
    
    @staticmethod
    async def recommend_schedule(
        miner_id: int,
        db: AsyncSession,
        target_hours: int = 12
    ) -> Dict[str, Any]:
        """
        Recommend optimal mining schedule for next 24 hours
        
        Args:
            miner_id: Miner ID
            db: Database session
            target_hours: Number of hours to mine in 24h period
        
        Returns:
            Dict with recommended schedule
        """
        # Get price forecast
        forecast = await EnergyOptimizationService.get_price_forecast(db, 24)
        
        if not forecast:
            return {"error": "No price forecast available"}
        
        # Sort by price (cheapest first)
        sorted_prices = sorted(forecast, key=lambda x: x["price_pence"])
        
        # Select cheapest slots
        recommended_slots = sorted_prices[:target_hours * 2]  # *2 because 30min slots
        
        # Calculate savings
        avg_expensive = sum(p["price_pence"] for p in sorted_prices[-target_hours * 2:]) / (target_hours * 2)
        avg_cheap = sum(p["price_pence"] for p in recommended_slots) / len(recommended_slots)
        savings_percent = ((avg_expensive - avg_cheap) / avg_expensive) * 100 if avg_expensive > 0 else 0
        
        return {
            "miner_id": miner_id,
            "target_hours": target_hours,
            "recommended_slots": recommended_slots,
            "avg_price_pence": round(avg_cheap, 2),
            "vs_random_avg": round(sum(p["price_pence"] for p in forecast) / len(forecast), 2),
            "savings_percent": round(savings_percent, 2)
        }
    
    @staticmethod
    async def should_mine_now(
        db: AsyncSession,
        cheap_threshold: float = 15.0,
        expensive_threshold: float = 25.0
    ) -> Dict[str, Any]:
        """
        Determine if current energy price is favorable for mining
        Uses three bands: CHEAP (< cheap_threshold), MODERATE (between), EXPENSIVE (>= expensive_threshold)
        
        Band Logic:
        - CHEAP: High/OC mode (mine at full power) - price < 15p
        - MODERATE: Low/Eco mode (reduce power consumption) - price 15-25p
        - EXPENSIVE: Off (stop mining to avoid high costs) - price 25p+
        
        Args:
            db: Database session
            cheap_threshold: Price threshold for CHEAP band (p/kWh)
            expensive_threshold: Price threshold for EXPENSIVE band (p/kWh)
        
        Returns:
            Dict with recommendation and band info
        """
        region = app_config.get("octopus_agile.region", "H")
        now = datetime.utcnow()
        
        # Get current price
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from <= now)
            .where(EnergyPrice.valid_to > now)
            .limit(1)
        )
        current_price = result.scalar_one_or_none()
        
        if not current_price:
            return {"error": "No current price available"}
        
        price = current_price.price_pence
        
        # Determine band
        if price < cheap_threshold:
            band = "CHEAP"
            mode = "high"  # High/OC mode
            recommendation = "Mine at full power (High/OC mode)"
        elif price >= expensive_threshold:
            band = "EXPENSIVE"
            mode = "off"  # Turn off
            recommendation = "Stop mining (too expensive)"
        else:
            band = "MODERATE"
            mode = "low"  # Low/Eco mode
            recommendation = "Reduce power (Low/Eco mode)"
        
        return {
            "band": band,
            "mode": mode,
            "current_price_pence": price,
            "cheap_threshold": cheap_threshold,
            "expensive_threshold": expensive_threshold,
            "recommendation": recommendation,
            "valid_until": current_price.valid_to.isoformat()
        }
